from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.agents.backlog_agent import generate_tasks
from app.ai.factory import resolve_provider
from app.ai.types import AIProviderError, ConfigurationError
from app.autopilot import select_task_for_autopilot
from app.config import Settings
from app.db import Database
from app.models import (
    AutonomyLevel,
    AutopilotPlanStatus,
    RunStatus,
    ScheduledRun,
    ScheduledRunStatus,
)
from app.orchestrator import RunOrchestrator
from app.planner import TaskPlanner
from app.repository import RepositoryAnalyzer

logger = logging.getLogger(__name__)

_RUN_STATUS_TO_SCHEDULED_STATUS = {
    RunStatus.pr_open: ScheduledRunStatus.completed,
    RunStatus.needs_human_review: ScheduledRunStatus.completed,
    RunStatus.failed: ScheduledRunStatus.failed,
    RunStatus.cancelled: ScheduledRunStatus.cancelled,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AutopilotScheduler:
    """A persistent, in-process background loop -- not a browser timer -- that survives the
    user closing their browser or signing out, since it lives in the FastAPI server process
    rather than any client. Each tick: reconciles scheduled runs it already started against
    their now-possibly-finished real Run, then processes any newly-due ones. Reuses the
    exact same analyzer/planner/backlog-agent/orchestrator the manual workflow already uses
    -- Autopilot is an unattended caller of that pipeline, not a second implementation of
    it."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        orchestrator: RunOrchestrator,
        tick_seconds: int = 30,
    ) -> None:
        self._db = db
        self._settings = settings
        self._orchestrator = orchestrator
        self._analyzer = RepositoryAnalyzer()
        self._planner = TaskPlanner()
        self._tick_seconds = tick_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Autopilot scheduler tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def tick(self) -> None:
        self._reconcile_in_flight()
        for scheduled_run in self._db.list_due_scheduled_runs(_now()):
            await self._process_due(scheduled_run)

    def _reconcile_in_flight(self) -> None:
        for scheduled_run in self._db.list_in_flight_scheduled_runs():
            run = self._db.get_run(scheduled_run.run_id) if scheduled_run.run_id else None
            if run is None or run.status in (RunStatus.queued, RunStatus.running):
                continue
            mapped = _RUN_STATUS_TO_SCHEDULED_STATUS.get(run.status, ScheduledRunStatus.failed)
            message = run.pr_url or run.error_message or f"Run finished: {run.status.value}"
            self._db.update_scheduled_run(
                scheduled_run.id, status=mapped, finished_at=_now(), result_message=message
            )

    async def _process_due(self, scheduled_run: ScheduledRun) -> None:
        plan = self._db.get_autopilot_plan_by_id(scheduled_run.plan_id)
        if plan is None or plan.status != AutopilotPlanStatus.active:
            self._db.update_scheduled_run(
                scheduled_run.id,
                status=ScheduledRunStatus.skipped,
                finished_at=_now(),
                result_message="Autopilot was paused or cancelled before this run started.",
            )
            return

        if self._db.has_active_run_for_repository(plan.repository_id):
            # Held back, not skipped -- retried on a later tick once the conflicting run
            # (started by Autopilot or manually) finishes. Never starts a second concurrent
            # run against the same repository.
            self._db.update_scheduled_run(scheduled_run.id, status=ScheduledRunStatus.waiting)
            return

        today = _now()[:10]
        if self._db.count_scheduled_runs_started_today(plan.id, today) >= plan.max_runs_per_day:
            self._db.update_scheduled_run(
                scheduled_run.id,
                status=ScheduledRunStatus.skipped,
                finished_at=_now(),
                result_message="Skipped -- this plan's maximum runs per day was already reached.",
            )
            return

        self._db.update_scheduled_run(scheduled_run.id, status=ScheduledRunStatus.running, started_at=_now())

        repository = self._db.get_repository(plan.repository_id)
        if repository is None:
            self._db.update_scheduled_run(
                scheduled_run.id,
                status=ScheduledRunStatus.failed,
                finished_at=_now(),
                result_message="Repository no longer exists.",
            )
            return

        try:
            analysis = self._analyzer.analyze(Path(repository.path))
        except ValueError as exc:
            self._db.update_scheduled_run(
                scheduled_run.id, status=ScheduledRunStatus.failed, finished_at=_now(),
                result_message=f"Repository analysis failed: {exc}",
            )
            return

        deterministic_plan = self._planner.plan(analysis)
        analysis_id = self._db.insert_analysis(plan.repository_id, analysis)
        self._db.sync_backlog_tasks(plan.repository_id, analysis_id, deterministic_plan.tasks)

        # Resolved once per scheduled run, from the plan owner's AI settings -- Autopilot may
        # run while that user is offline, so this must never depend on anything from the
        # current request/session. A broken or incomplete configuration must not crash the
        # scheduler loop: it's recorded as this one scheduled run failing/being skipped, and
        # the next tick carries on with everything else.
        try:
            user_settings = self._db.get_user_ai_settings(plan.owner_login)
            ai_provider = resolve_provider(user_settings, self._settings)
        except AIProviderError as exc:
            status = ScheduledRunStatus.skipped if isinstance(exc, ConfigurationError) else ScheduledRunStatus.failed
            self._db.update_scheduled_run(scheduled_run.id, status=status, finished_at=_now(), result_message=str(exc))
            return

        # Best-effort, same as the manual "Generate tasks with AI" button -- generate_tasks()
        # already swallows its own failures and returns [], so a flaky model here degrades to
        # just the deterministic candidates rather than failing the whole scheduled run.
        proposed = await generate_tasks(Path(repository.path), analysis, ai_provider=ai_provider)
        if proposed:
            self._db.sync_backlog_tasks(plan.repository_id, analysis_id, proposed)

        tasks = self._db.list_tasks_for_repository(plan.repository_id)
        chosen = select_task_for_autopilot(tasks, plan.focus_areas)

        if chosen is None:
            # Not an error -- an unattended system that invents busywork when there's
            # nothing worth doing is worse than one that does nothing.
            self._db.update_scheduled_run(
                scheduled_run.id, status=ScheduledRunStatus.skipped, finished_at=_now(),
                result_message="Repository analyzed -- no suitable work found for your focus areas.",
            )
            return

        self._db.update_scheduled_run(scheduled_run.id, task_id=chosen.id)

        if plan.autonomy_level == AutonomyLevel.conservative:
            self._db.update_scheduled_run(
                scheduled_run.id, status=ScheduledRunStatus.completed, finished_at=_now(),
                result_message=f'Found candidate task "{chosen.title}" -- awaiting your approval in the backlog.',
            )
            return

        # balanced and autopilot both auto-approve and run the top matching task -- the
        # spec's distinction between them ("finds appropriate tasks" vs. "finds and ranks
        # tasks") isn't a concrete, testable selection algorithm difference, so this first
        # implementation treats the actual pipeline identically for both rather than
        # fabricating a fake ranking step; only the selection *pool* (focus areas the user
        # approved) differs run to run.
        try:
            self._db.approve_task(chosen.id)
            run_id = self._orchestrator.submit(chosen.id, triggered_by="autopilot", owner_login=plan.owner_login)
        except ValueError as exc:
            self._db.update_scheduled_run(
                scheduled_run.id, status=ScheduledRunStatus.failed, finished_at=_now(), result_message=str(exc)
            )
            return

        self._db.update_scheduled_run(
            scheduled_run.id, run_id=run_id, result_message=f'Started: "{chosen.title}"'
        )
        asyncio.create_task(self._orchestrator.execute(run_id))
        # Status stays 'running' here -- _reconcile_in_flight() above promotes it to
        # completed/failed/cancelled on a later tick once the real Run reaches a terminal
        # state, since that pipeline runs independently and can take minutes.
