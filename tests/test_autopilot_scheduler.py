import asyncio
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.autopilot_scheduler import AutopilotScheduler
from app.config import Settings
from app.db import Database
from app.events import EventBus
from app.models import (
    AutonomyLevel,
    AutopilotPlanRequest,
    AutopilotPlanStatus,
    FocusArea,
    RunStatus,
    ScheduledRunStatus,
    ScheduleType,
)
from app.orchestrator import RunOrchestrator


def _init_repo_with_a_bug_fix_todo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "app.py").write_text("# TODO: fix bug in the crash handler\ndef f():\n    pass\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _request(**overrides) -> AutopilotPlanRequest:
    defaults = {
        "schedule_type": ScheduleType.daily,
        "run_time": "09:00",
        "timezone": "UTC",
        "focus_areas": [FocusArea.bug_fixes],
        "autonomy_level": AutonomyLevel.balanced,
    }
    defaults.update(overrides)
    return AutopilotPlanRequest(**defaults)


def _settings(tmp_path: Path, db_path: Path) -> Settings:
    base = Settings.from_environment()
    import dataclasses

    return dataclasses.replace(base, workspace_root=tmp_path, db_path=db_path)


def _build(tmp_path: Path) -> tuple[Database, AutopilotScheduler, RunOrchestrator]:
    db = Database(tmp_path / "test.db")
    settings = _settings(tmp_path, tmp_path / "test.db")
    orchestrator = RunOrchestrator(db, settings, EventBus())
    scheduler = AutopilotScheduler(db, settings, orchestrator)
    return db, scheduler, orchestrator


def _empty_tasks_response() -> dict:
    return {"message": {"content": '{"tasks": []}'}}


async def _await_spawned_tasks(before: set[asyncio.Task]) -> None:
    new_tasks = asyncio.all_tasks() - before - {asyncio.current_task()}
    if new_tasks:
        await asyncio.gather(*new_tasks, return_exceptions=True)


def test_tick_skips_a_due_run_when_the_plan_is_paused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.paused)
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(scheduled.id)
    assert result.status == ScheduledRunStatus.skipped
    assert "paused" in result.result_message.lower()


def test_tick_holds_back_a_due_run_when_the_repository_already_has_an_active_run(tmp_path: Path) -> None:
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    # A conflicting run already in flight for this repository.
    from app.models import ProjectAnalysis, RiskLevel, Task

    analysis = ProjectAnalysis(
        root=str(repo), languages={}, manifests=[], readme_present=False, test_directories=[],
        todo_items=[], source_files=0, ignored_files=0, detected_tools=[], summary="",
    )
    analysis_id = db.insert_analysis(repository_id, analysis)
    task = Task(id="other-task", title="x", description="y", priority=3, risk=RiskLevel.low, source="repository-todo")
    db.sync_backlog_tasks(repository_id, analysis_id, [task])
    db.approve_task("other-task")
    db.create_run("other-run", "other-task")

    asyncio.run(scheduler.tick())

    assert db.get_scheduled_run(scheduled.id).status == ScheduledRunStatus.waiting


def test_tick_skips_when_the_plans_daily_run_cap_is_reached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ollama.AsyncClient", _fake_client_returning(_empty_tasks_response()))
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request(max_runs_per_day=1))
    already_started, due = db.create_scheduled_runs(
        plan.id, repository_id, [_past_iso(minutes=10), _past_iso(minutes=1)]
    )
    db.update_scheduled_run(
        already_started.id, status=ScheduledRunStatus.completed, started_at=_now_iso(), finished_at=_now_iso()
    )

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(due.id)
    assert result.status == ScheduledRunStatus.skipped
    assert "maximum runs per day" in result.result_message.lower()


def test_tick_skips_with_no_error_when_no_task_matches_the_focus_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ollama.AsyncClient", _fake_client_returning(_empty_tasks_response()))
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    # The deterministic planner proposes several candidates for a bare repo like this one
    # (a bug-fix TODO, a missing-README task, a missing-tests task) -- none of them are
    # ever going to be classified as "security" or "performance" work, so this genuinely
    # has no match regardless of exactly which candidates it generates.
    plan = db.upsert_autopilot_plan(
        "plan-1", repository_id, "octocat", _request(focus_areas=[FocusArea.security, FocusArea.performance])
    )
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(scheduled.id)
    assert result.status == ScheduledRunStatus.skipped
    assert "no suitable work" in result.result_message.lower()


def test_tick_marks_the_scheduled_run_skipped_when_the_plan_owners_ai_settings_are_broken(
    tmp_path: Path,
) -> None:
    # The plan owner saved Anthropic as their provider but the stored settings row somehow
    # has no usable API key (e.g. a corrupted/incomplete save) -- this must surface as this
    # one scheduled run being skipped with a clear reason, never as a crashed scheduler tick
    # that would also block every other repository's due runs behind it.
    from app.models import AIProviderName

    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    db.upsert_user_ai_settings("octocat", AIProviderName.anthropic, "claude-sonnet-5", None, None)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(scheduled.id)
    assert result.status == ScheduledRunStatus.skipped
    assert "api key" in result.result_message.lower()


def test_conservative_mode_finds_a_task_but_does_not_start_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ollama.AsyncClient", _fake_client_returning(_empty_tasks_response()))
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan(
        "plan-1", repository_id, "octocat", _request(autonomy_level=AutonomyLevel.conservative)
    )
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(scheduled.id)
    assert result.status == ScheduledRunStatus.completed
    assert result.task_id is not None
    assert result.run_id is None
    assert "awaiting your approval" in result.result_message.lower()
    assert db.get_task(result.task_id).status == "backlog"  # never auto-approved


def test_balanced_mode_approves_and_starts_a_real_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(
        side_effect=[
            _empty_tasks_response(),  # backlog agent
            {"message": {"role": "assistant", "content": "No changes needed.", "tool_calls": None}},  # coding agent
            {"message": {"content": '{"type": "chore", "scope": "", "subject": "no-op"}'}},  # (unreached if no diff)
        ]
    )

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return await chat(**kwargs)

    monkeypatch.setattr("ollama.AsyncClient", FakeClient)

    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request(autonomy_level=AutonomyLevel.balanced))
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    async def scenario() -> None:
        before = asyncio.all_tasks()
        await scheduler.tick()
        await _await_spawned_tasks(before)

    asyncio.run(scenario())

    result = db.get_scheduled_run(scheduled.id)
    assert result.task_id is not None
    assert result.run_id is not None
    run = db.get_run(result.run_id)
    assert run.triggered_by == "autopilot"
    assert db.get_task(result.task_id).status != "backlog"  # was approved


def test_reconciliation_promotes_a_running_scheduled_run_once_the_real_run_finishes(tmp_path: Path) -> None:
    db, scheduler, _ = _build(tmp_path)
    repo = tmp_path / "repo"
    _init_repo_with_a_bug_fix_todo(repo)
    repository_id = db.upsert_repository(str(repo), "octocat")
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    [scheduled] = db.create_scheduled_runs(plan.id, repository_id, [_past_iso()])

    from app.models import ProjectAnalysis, RiskLevel, Task

    analysis = ProjectAnalysis(
        root=str(repo), languages={}, manifests=[], readme_present=False, test_directories=[],
        todo_items=[], source_files=0, ignored_files=0, detected_tools=[], summary="",
    )
    analysis_id = db.insert_analysis(repository_id, analysis)
    task = Task(id="t1", title="x", description="y", priority=3, risk=RiskLevel.low, source="repository-todo")
    db.sync_backlog_tasks(repository_id, analysis_id, [task])
    db.approve_task("t1")
    db.create_run("run-1", "t1", triggered_by="autopilot")
    db.update_run("run-1", status=RunStatus.pr_open, pr_url="https://example.com/pr/1", finished_at=_now_iso())
    db.update_scheduled_run(scheduled.id, status=ScheduledRunStatus.running, run_id="run-1", started_at=_now_iso())

    asyncio.run(scheduler.tick())

    result = db.get_scheduled_run(scheduled.id)
    assert result.status == ScheduledRunStatus.completed
    assert result.result_message == "https://example.com/pr/1"


def _past_iso(minutes: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _fake_client_returning(response: dict):
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return response

    return FakeClient
