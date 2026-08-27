from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path

from app.agents.coding_agent import CodingAgent, CodingAgentError
from app.agents.commit_message import generate_commit_message
from app.agents.file_tools import FileTools, PathGuard
from app.agents.review_agent import review_diff
from app.ai.base import AIProvider
from app.ai.factory import resolve_provider
from app.ai.types import AIProviderError
from app.config import Settings
from app.db import Database
from app.events import EventBus
from app.git_ops import (
    GitOpsError,
    commit_all,
    create_worktree,
    diff_against_base,
    diff_working_tree,
    get_remote_url,
    push,
    resolve_default_branch,
)
from app.github_client import (
    GitHubClientError,
    ensure_repo_allowed,
    open_draft_pull_request,
    parse_repo_slug,
)
from app.models import ReviewResult, RunStatus, Task, TaskStatus, TestOutcome
from app.test_runner import AllowlistedTestRunner

MAX_CODING_ATTEMPTS = 3  # 1 initial attempt + up to 2 repair retries on test failure


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RunOrchestrator:
    """Coordinates the run pipeline for approved tasks, gated by a concurrency semaphore.

    For an approved task: isolate a fresh git worktree, run the local coding agent (bounded
    to MAX_CODING_ATTEMPTS attempts, re-running the repository's allowlisted tests after each
    one and feeding failures back for a repair attempt), commit on success with a generated
    Conventional Commits message, run an advisory review, and -- only if the target repo is
    on ALLOWED_TARGET_REPOS and a token is configured -- push the branch and open a draft PR.
    Every step lands the run in a clean terminal status; merging always stays a human, on
    GitHub, outside this app entirely."""

    def __init__(self, db: Database, settings: Settings, event_bus: EventBus) -> None:
        self._db = db
        self._settings = settings
        self._events = event_bus
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
        self._test_runner = AllowlistedTestRunner(timeout_seconds=settings.test_timeout_seconds)
        # Holds the run-starter's own GitHub OAuth token in memory only, from submit() until
        # _try_open_pull_request() consumes it -- never persisted to the DB or logged. Lets
        # each run push with the token of whoever actually started it, without needing a
        # separate credentials table.
        self._pending_push_tokens: dict[str, str] = {}
        # Tracks the asyncio Task actually executing each in-flight run's execute() call, so
        # cancel() can interrupt it. This works whether execute() is awaited directly (tests),
        # via FastAPI's BackgroundTasks (the real API, which awaits it within the same Task
        # that has handled the request since it started), or via asyncio.create_task() -- in
        # every case asyncio.current_task() inside execute() resolves to that same Task.
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    def submit(
        self,
        task_id: str,
        github_token: str | None = None,
        triggered_by: str | None = None,
        owner_login: str | None = None,
    ) -> str:
        """Validates the task is approved and records a queued run. Does not execute
        anything -- the caller schedules execute() as a background task. github_token, if
        given, is the run-starter's own GitHub OAuth token: it takes priority over the
        static GITHUB_TOKEN/ALLOWED_TARGET_REPOS for this run's push/PR step. triggered_by
        records who/what started the run (e.g. "autopilot") for the UI to label -- a plain
        manual start leaves it None. owner_login is whose AI settings this run should use
        (resolved once execute() actually starts, via app.ai.factory.resolve_provider) --
        manual starts pass the logged-in user, Autopilot passes the plan's owner."""
        task = self._db.get_task(task_id)
        if task is None:
            raise ValueError("Task not found")
        if task.status != TaskStatus.approved:
            raise ValueError(f"Task must be approved before starting a run (currently {task.status.value})")
        run_id = uuid.uuid4().hex
        self._db.create_run(run_id, task_id, triggered_by=triggered_by, owner_login=owner_login)
        if github_token:
            self._pending_push_tokens[run_id] = github_token
        return run_id

    async def execute(self, run_id: str) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._active_tasks[run_id] = current_task
        try:
            async with self._semaphore:
                await self._execute(run_id)
        except asyncio.CancelledError:
            await self._mark_cancelled(run_id)
            raise
        finally:
            self._active_tasks.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        """Requests cancellation of a run that is currently queued (waiting on the
        concurrency semaphore) or actively executing. Returns False if the run isn't
        tracked -- already finished, never started, or orphaned by a server restart
        (reconcile_orphaned_runs() already marks those failed at startup) -- so the caller
        can tell "nothing to cancel" apart from a real failure."""
        task = self._active_tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def _mark_cancelled(self, run_id: str) -> None:
        run = self._db.get_run(run_id)
        self._db.update_run(run_id, status=RunStatus.cancelled, finished_at=_now())
        if run is not None:
            self._db.set_task_status(run.task_id, TaskStatus.cancelled)
        await self._log(run_id, "cancelled", "warning", "Run was cancelled")

    async def _execute(self, run_id: str) -> None:
        run = self._db.get_run(run_id)
        task = self._db.get_task(run.task_id)
        self._db.update_run(run_id, status=RunStatus.running, started_at=_now())
        self._db.set_task_status(task.id, TaskStatus.running)
        await self._log(run_id, "setup", "info", "Run started")

        try:
            return await self._execute_inner(run_id, task)
        finally:
            # _try_open_pull_request() already pops this on the path that reaches it -- this
            # is the safety net for every path that doesn't (test failures, no-op coding
            # agent, an exception before that point), so a pending token can never outlive
            # its run in memory.
            self._pending_push_tokens.pop(run_id, None)

    async def _execute_inner(self, run_id: str, task: Task) -> None:
        try:
            run = self._db.get_run(run_id)
            user_settings = self._db.get_user_ai_settings(run.owner_login) if run and run.owner_login else None
            ai_provider = resolve_provider(user_settings, self._settings)
            self._db.update_run(run_id, ai_provider=ai_provider.provider_name.value, ai_model=ai_provider.model)
            await self._log(
                run_id, "setup", "info", f"Using AI provider {ai_provider.provider_name.value} ({ai_provider.model})"
            )

            repository = self._db.get_repository(task.repository_id)
            analysis = self._db.get_latest_analysis(task.repository_id)
            repo_path = Path(repository.path)

            base_branch = await asyncio.to_thread(resolve_default_branch, repo_path)
            worktree_path, branch_name = await asyncio.to_thread(
                create_worktree,
                repo_path,
                self._settings.workspace_root / ".worktrees",
                run_id,
                task.title,
                base_branch,
            )
            self._db.update_run(
                run_id, branch_name=branch_name, worktree_path=str(worktree_path), base_branch=base_branch
            )
            await self._log(run_id, "worktree", "info", f"Created isolated worktree on branch {branch_name}")

            detected_tools = analysis.detected_tools if analysis else []
            tools = FileTools(PathGuard(worktree_path))

            gating_tools: set[str] = set()
            if detected_tools:
                await self._log(run_id, "baseline", "info", "Running baseline checks before any changes")
                baseline_outcomes = await self._run_tests(run_id, worktree_path, detected_tools, phase="baseline")
                gating_tools = {o.tool for o in baseline_outcomes if o.exit_code == 0}
                pre_existing = [o.tool for o in baseline_outcomes if o.exit_code != 0]
                if pre_existing:
                    await self._log(
                        run_id,
                        "baseline",
                        "info",
                        f"Pre-existing failures, won't block this run: {', '.join(pre_existing)}",
                    )

            async def run_tests_tool() -> list[dict]:
                outcomes = await self._run_tests(run_id, worktree_path, detected_tools, gating_tools=gating_tools)
                return [
                    {**outcome.model_dump(), "blocking": outcome.exit_code != 0 and outcome.tool in gating_tools}
                    for outcome in outcomes
                ]

            def log_coding_event(level: str, message: str, data: dict | None) -> Awaitable[None]:
                return self._log(run_id, "coding", level, message, data)

            coding_agent = CodingAgent(
                ai_provider,
                max_iterations=self._settings.coding_agent_max_iterations,
                timeout_seconds=self._settings.coding_agent_timeout_seconds,
            )

            failure_context: str | None = None
            outcomes: list[TestOutcome] = []
            for attempt in range(1, MAX_CODING_ATTEMPTS + 1):
                await self._log(
                    run_id, "coding", "info", f"Coding agent attempt {attempt}/{MAX_CODING_ATTEMPTS} starting"
                )
                try:
                    result = await coding_agent.run(
                        task, tools, run_tests_tool, failure_context=failure_context, log=log_coding_event
                    )
                    await self._log(
                        run_id,
                        "coding",
                        "info",
                        f"Coding agent attempt {attempt} finished ({result.tool_calls} tool call(s)): "
                        f"{result.summary or '(no summary)'}",
                    )
                except CodingAgentError as exc:
                    await self._log(run_id, "coding", "warning", str(exc))

                outcomes = await self._run_tests(run_id, worktree_path, detected_tools, gating_tools=gating_tools)
                blocking = self._blocking_failures(outcomes, gating_tools)
                if not blocking or attempt == MAX_CODING_ATTEMPTS:
                    break
                failure_context = "\n\n".join(
                    f"{outcome.tool} failed (exit {outcome.exit_code}):\n{(outcome.stdout + outcome.stderr)[-2000:]}"
                    for outcome in blocking
                )
                await self._log(run_id, "coding", "warning", "Tests failed -- retrying with failure context")

            tests_failed = bool(self._blocking_failures(outcomes, gating_tools))

            commit_sha: str | None = None
            if not tests_failed:
                diff_text = await asyncio.to_thread(diff_working_tree, worktree_path)
                if diff_text.strip():
                    message = await generate_commit_message(task, diff_text, ai_provider=ai_provider)
                    commit_sha = await asyncio.to_thread(commit_all, worktree_path, message)
                    if commit_sha:
                        self._db.update_run(run_id, commit_sha=commit_sha)
                        await self._log(run_id, "commit", "info", f"Committed {commit_sha[:12]}: {message}")

            pr_url: str | None = None
            if commit_sha is not None:
                pr_url = await self._try_open_pull_request(
                    run_id, task, worktree_path, branch_name, base_branch, ai_provider
                )

            if tests_failed:
                final_status = RunStatus.failed
                error_message = "Tests still failing after coding agent repair attempts"
            elif commit_sha is None:
                final_status = RunStatus.failed
                error_message = "Coding agent made no changes"
            elif pr_url is not None:
                final_status = RunStatus.pr_open
                error_message = None
            else:
                final_status = RunStatus.needs_human_review
                error_message = None

            self._db.update_run(run_id, status=final_status, finished_at=_now(), error_message=error_message)
            task_status = {
                RunStatus.pr_open: TaskStatus.pr_open,
                RunStatus.needs_human_review: TaskStatus.needs_human_review,
            }.get(final_status, TaskStatus.failed)
            self._db.set_task_status(task.id, task_status)
            await self._log(run_id, "complete", "info", f"Run finished with status {final_status.value}")
        except Exception as exc:  # noqa: BLE001 -- must always leave the run/task in a terminal,
            # visible state (never stuck at "running") since this executes as a fire-and-forget
            # background task with no caller left to observe an unhandled exception.
            self._db.update_run(run_id, status=RunStatus.failed, finished_at=_now(), error_message=str(exc))
            self._db.set_task_status(task.id, TaskStatus.failed)
            level = "warning" if isinstance(exc, (GitOpsError, AIProviderError)) else "error"
            await self._log(run_id, "error", level, str(exc))

    async def _try_open_pull_request(
        self, run_id: str, task: Task, worktree_path: Path, branch_name: str, base_branch: str, ai_provider: AIProvider
    ) -> str | None:
        """Best-effort: pushes the branch and opens a draft PR if a usable token is
        available. Any failure here -- no remote, not allowlisted, no token, or the
        push/API call itself failing -- degrades to "needs_human_review" rather than
        "failed": the code change is already safely committed locally either way, it just
        didn't get automatically published."""
        # Popped unconditionally (not just on the success path) so it's never left behind
        # in memory regardless of what happens next.
        run_token = self._pending_push_tokens.pop(run_id, None)

        remote_url = await asyncio.to_thread(get_remote_url, worktree_path)
        if remote_url is None:
            await self._log(run_id, "pr", "info", "No GitHub remote configured -- the commit is ready locally.")
            return None
        try:
            repo_slug = parse_repo_slug(remote_url)
        except GitHubClientError as exc:
            await self._log(run_id, "pr", "info", f"{exc} -- the commit is ready locally.")
            return None

        if run_token:
            # This run was started from a repo picked via the GitHub repo list -- the
            # run-starter's own OAuth token is the credential, and GitHub's own permissions
            # on it (not the static ALLOWED_TARGET_REPOS allowlist, which exists for the
            # separate GITHUB_TOKEN/.env flow) are the real boundary on what it can push to.
            token = run_token
        else:
            try:
                ensure_repo_allowed(repo_slug, self._settings.allowed_target_repos)
            except GitHubClientError as exc:
                await self._log(run_id, "pr", "info", f"{exc} -- the commit is ready locally.")
                return None
            if not self._settings.github_token:
                await self._log(
                    run_id, "pr", "warning", f"{repo_slug} is allowlisted but GITHUB_TOKEN is not configured."
                )
                return None
            token = self._settings.github_token

        diff_text = await asyncio.to_thread(diff_against_base, worktree_path, base_branch)
        review = await review_diff(task, diff_text, ai_provider=ai_provider)
        self._db.update_run(run_id, review_result=review)
        await self._log(
            run_id,
            "review",
            "info",
            f"Review: {'approved' if review.approved else 'flagged'} ({review.risk.value}) -- {review.summary}",
            data=review.model_dump(),
        )

        try:
            await asyncio.to_thread(push, worktree_path, branch_name, token)
            await self._log(run_id, "pr", "info", f"Pushed branch {branch_name}")
            body = self._pr_body(task, review)
            pr = await open_draft_pull_request(repo_slug, branch_name, base_branch, task.title, body, token)
        except (GitOpsError, GitHubClientError) as exc:
            await self._log(run_id, "pr", "warning", f"Push/PR failed, changes remain committed locally: {exc}")
            return None

        pr_url = pr.get("html_url")
        self._db.update_run(run_id, pr_url=pr_url)
        await self._log(run_id, "pr", "info", f"Opened draft PR: {pr_url}")
        return pr_url

    @staticmethod
    def _pr_body(task: Task, review: ReviewResult) -> str:
        concerns = "\n".join(f"- {concern}" for concern in review.concerns) or "- (none noted)"
        verdict = "approved" if review.approved else "flagged for attention"
        return (
            f"{task.description}\n\n"
            f"---\n"
            f"**Automated review** ({review.risk.value} risk, {verdict}):\n{review.summary}\n\n"
            f"Concerns:\n{concerns}\n\n"
            f"---\n_Generated by PR Engineer -- requires human review before merge._"
        )

    async def _run_tests(
        self,
        run_id: str,
        worktree_path: Path,
        detected_tools: list[str],
        *,
        phase: str = "test",
        gating_tools: set[str] | None = None,
    ) -> list[TestOutcome]:
        outcomes = await asyncio.to_thread(self._test_runner.run, worktree_path, detected_tools)
        for outcome in outcomes:
            if outcome.exit_code == 0:
                level, suffix = "info", ""
            elif gating_tools is not None and outcome.tool not in gating_tools:
                level, suffix = "info", " (pre-existing, not required to fix)"
            else:
                level, suffix = "warning", ""
            await self._log(
                run_id, phase, level, f"{outcome.tool} exited {outcome.exit_code}{suffix}", data=outcome.model_dump()
            )
        self._db.update_run(run_id, test_results=outcomes)
        return outcomes

    @staticmethod
    def _blocking_failures(outcomes: list[TestOutcome], gating_tools: set[str]) -> list[TestOutcome]:
        # Only a tool that was passing before the coding agent touched anything counts as a
        # blocker -- a repo-wide pre-existing failure unrelated to the task would otherwise
        # make every task on that repo unwinnable regardless of code quality.
        return [o for o in outcomes if o.exit_code != 0 and o.tool in gating_tools]

    async def _log(self, run_id: str, phase: str, level: str, message: str, data: dict | None = None) -> None:
        event = self._db.add_event(run_id, phase, level, message, data)
        await self._events.publish(run_id, event)
