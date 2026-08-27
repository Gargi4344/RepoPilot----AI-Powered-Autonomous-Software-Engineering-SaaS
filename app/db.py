from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models import (
    AIProviderName,
    AutonomyLevel,
    AutopilotPlan,
    AutopilotPlanRequest,
    AutopilotPlanStatus,
    FocusArea,
    ProjectAnalysis,
    RepositorySummary,
    ReviewResult,
    RiskLevel,
    Run,
    RunEvent,
    RunStatus,
    ScheduledRun,
    ScheduledRunStatus,
    ScheduleType,
    Task,
    TaskStatus,
    TestOutcome,
    UserAISettings,
)

_RUN_UPDATABLE_COLUMNS = {
    "status",
    "branch_name",
    "worktree_path",
    "base_branch",
    "target_repo_slug",
    "started_at",
    "finished_at",
    "pr_url",
    "pr_number",
    "review_result_json",
    "error_message",
    "input_tokens",
    "output_tokens",
    "test_results_json",
    "commit_sha",
    "ai_provider",
    "ai_model",
}

_SCHEDULED_RUN_UPDATABLE_COLUMNS = {
    "status",
    "task_id",
    "run_id",
    "result_message",
    "started_at",
    "finished_at",
    "scheduled_at",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

-- Which logged-in GitHub users have analyzed a given repository. A repository row is shared
-- (one clone/path can be analyzed by several users), but each user should only ever see
-- repositories they themselves analyzed -- this join table is what "Previously analyzed"
-- filters against, instead of listing every repository ever analyzed by anyone on the server.
CREATE TABLE IF NOT EXISTS repository_access (
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    owner_login TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(repository_id, owner_login)
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    created_at TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    analysis_id INTEGER NOT NULL REFERENCES analyses(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority INTEGER NOT NULL,
    risk TEXT NOT NULL,
    affected_files_json TEXT NOT NULL,
    required_checks_json TEXT NOT NULL,
    source TEXT NOT NULL,
    requires_human_approval INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'backlog',
    approved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    status TEXT NOT NULL,
    triggered_by TEXT,
    owner_login TEXT,
    branch_name TEXT,
    worktree_path TEXT,
    base_branch TEXT,
    target_repo_slug TEXT,
    started_at TEXT,
    finished_at TEXT,
    pr_url TEXT,
    pr_number INTEGER,
    review_result_json TEXT,
    error_message TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    test_results_json TEXT,
    commit_sha TEXT,
    ai_provider TEXT,
    ai_model TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id),
    ts TEXT NOT NULL,
    phase TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT
);

-- One plan per repository: activating Autopilot again replaces this row's settings rather
-- than creating a second plan, matching "configure a repository once."
CREATE TABLE IF NOT EXISTS autopilot_plans (
    id TEXT PRIMARY KEY,
    repository_id INTEGER NOT NULL UNIQUE REFERENCES repositories(id),
    owner_login TEXT NOT NULL,
    status TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    run_time TEXT NOT NULL,
    timezone TEXT NOT NULL,
    weekly_day INTEGER,
    custom_days_json TEXT NOT NULL,
    max_runs_per_day INTEGER NOT NULL,
    focus_areas_json TEXT NOT NULL,
    autonomy_level TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Each row is one concrete, individually trackable/cancellable slot within a plan's bounded
-- 7-day window -- not a recurring cron entry. A plan whose window has fully played out (no
-- more 'scheduled' rows) simply does nothing further until the user re-activates it.
CREATE TABLE IF NOT EXISTS autopilot_scheduled_runs (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES autopilot_plans(id),
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id),
    run_id TEXT REFERENCES runs(id),
    result_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);

-- One row per user: RepoPilot deliberately does not support per-operation model routing --
-- whatever provider/model is configured here is used for every AI operation belonging to
-- that user (repository analysis task proposals, coding, commit messages, review).
CREATE TABLE IF NOT EXISTS user_ai_settings (
    owner_login TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    encrypted_api_key TEXT,
    endpoint TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    """Owns the SQLite file and schema backing PR Engineer's persisted state."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        # CREATE TABLE IF NOT EXISTS never alters a table that already exists on disk from
        # before this column was added -- a real dev/prod database predates triggered_by.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        if "triggered_by" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN triggered_by TEXT")
        if "owner_login" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN owner_login TEXT")
        if "ai_provider" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN ai_provider TEXT")
        if "ai_model" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN ai_model TEXT")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_repository(self, path: str, owner_login: str) -> int:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO repositories (path, created_at) VALUES (?, ?) "
                "ON CONFLICT(path) DO NOTHING",
                (path, _now()),
            )
            row = conn.execute("SELECT id FROM repositories WHERE path = ?", (path,)).fetchone()
            repository_id = int(row["id"])
            conn.execute(
                "INSERT INTO repository_access (repository_id, owner_login, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(repository_id, owner_login) DO NOTHING",
                (repository_id, owner_login, _now()),
            )
            return repository_id

    def list_repositories(self, owner_login: str) -> list[RepositorySummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.id, r.path, r.created_at FROM repositories r "
                "JOIN repository_access a ON a.repository_id = r.id "
                "WHERE a.owner_login = ? ORDER BY a.created_at DESC",
                (owner_login,),
            ).fetchall()
            return [RepositorySummary(id=row["id"], path=row["path"], created_at=row["created_at"]) for row in rows]

    def user_can_access_repository(self, repository_id: int, owner_login: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM repository_access WHERE repository_id = ? AND owner_login = ?",
                (repository_id, owner_login),
            ).fetchone()
            return row is not None

    def insert_analysis(self, repository_id: int, analysis: ProjectAnalysis) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO analyses (repository_id, created_at, analysis_json, summary) VALUES (?, ?, ?, ?)",
                (repository_id, _now(), analysis.model_dump_json(), analysis.summary),
            )
            return int(cursor.lastrowid)

    def sync_backlog_tasks(self, repository_id: int, analysis_id: int, tasks: list[Task]) -> None:
        """Insert newly-planned tasks. Tasks already recorded (same content-derived id) are left untouched,
        so a task that has moved past backlog (approved/running/...) is never reset by a fresh analysis."""
        with self._connect() as conn:
            for task in tasks:
                conn.execute(
                    "INSERT INTO tasks (id, repository_id, analysis_id, title, description, priority, risk, "
                    "affected_files_json, required_checks_json, source, requires_human_approval, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (
                        task.id, repository_id, analysis_id, task.title, task.description, task.priority,
                        task.risk.value, json.dumps(task.affected_files), json.dumps(task.required_checks),
                        task.source, int(task.requires_human_approval), TaskStatus.backlog.value, _now(),
                    ),
                )

    def list_tasks_for_repository(self, repository_id: int) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE repository_id = ? ORDER BY priority DESC, created_at ASC",
                (repository_id,),
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._row_to_task(row) if row else None

    def approve_task(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            if row["status"] != TaskStatus.backlog.value:
                raise ValueError(f"Task {task_id} is not in backlog status (currently {row['status']})")
            approved_at = _now()
            conn.execute(
                "UPDATE tasks SET status = ?, approved_at = ? WHERE id = ?",
                (TaskStatus.approved.value, approved_at, task_id),
            )
            return self._row_to_task(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    def get_repository(self, repository_id: int) -> RepositorySummary | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, path, created_at FROM repositories WHERE id = ?", (repository_id,)
            ).fetchone()
            return RepositorySummary(id=row["id"], path=row["path"], created_at=row["created_at"]) if row else None

    def get_latest_analysis(self, repository_id: int) -> ProjectAnalysis | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT analysis_json FROM analyses WHERE repository_id = ? ORDER BY created_at DESC LIMIT 1",
                (repository_id,),
            ).fetchone()
            return ProjectAnalysis.model_validate_json(row["analysis_json"]) if row else None

    def get_latest_analysis_id(self, repository_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM analyses WHERE repository_id = ? ORDER BY created_at DESC LIMIT 1",
                (repository_id,),
            ).fetchone()
            return row["id"] if row else None

    def set_task_status(self, task_id: str, status: TaskStatus) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status.value, task_id))

    def create_run(
        self,
        run_id: str,
        task_id: str,
        triggered_by: str | None = None,
        owner_login: str | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, task_id, status, triggered_by, owner_login, ai_provider, ai_model, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, task_id, RunStatus.queued.value, triggered_by, owner_login, ai_provider, ai_model, _now()),
            )

    def update_run(self, run_id: str, **fields: object) -> None:
        if not fields:
            return
        if "test_results" in fields:
            outcomes = fields.pop("test_results")
            fields["test_results_json"] = json.dumps([o.model_dump() for o in outcomes])
        if "review_result" in fields:
            review = fields.pop("review_result")
            fields["review_result_json"] = json.dumps(review.model_dump()) if review is not None else None
        if "status" in fields and isinstance(fields["status"], RunStatus):
            fields["status"] = fields["status"].value
        unknown = set(fields) - _RUN_UPDATABLE_COLUMNS
        if unknown:
            raise ValueError(f"Cannot update unknown run column(s): {sorted(unknown)}")
        assignments = ", ".join(f"{column} = ?" for column in fields)
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*fields.values(), run_id))

    def get_run(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return self._row_to_run(row) if row else None

    def list_runs_for_task(self, task_id: str) -> list[Run]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE task_id = ? ORDER BY created_at DESC", (task_id,)
            ).fetchall()
            return [self._row_to_run(row) for row in rows]

    def reconcile_orphaned_runs(self) -> list[str]:
        """Marks any run left at queued/running as failed. Those statuses only ever advance
        via the async task that owns them -- if the process that was running it crashed or
        was restarted, that task is gone and nothing will ever move the row again, leaving
        it stuck forever (and permanently inflating the active-run count) unless a fresh
        startup cleans it up. Returns the reconciled run ids, for startup logging."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, task_id FROM runs WHERE status IN (?, ?)",
                (RunStatus.queued.value, RunStatus.running.value),
            ).fetchall()
            if not rows:
                return []
            now = _now()
            conn.executemany(
                "UPDATE runs SET status = ?, error_message = ?, finished_at = ? WHERE id = ?",
                [
                    (RunStatus.failed.value, "Run was interrupted by a server restart", now, row["id"])
                    for row in rows
                ],
            )
            task_ids = {row["task_id"] for row in rows}
            conn.executemany(
                "UPDATE tasks SET status = ? WHERE id = ? AND status = ?",
                [(TaskStatus.failed.value, task_id, TaskStatus.running.value) for task_id in task_ids],
            )
            return [row["id"] for row in rows]

    def count_active_runs(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM runs WHERE status IN (?, ?) GROUP BY status",
                (RunStatus.queued.value, RunStatus.running.value),
            ).fetchall()
            return {row["status"]: row["n"] for row in rows}

    def add_event(self, run_id: str, phase: str, level: str, message: str, data: dict | None = None) -> RunEvent:
        ts = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO run_events (run_id, ts, phase, level, message, data_json) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, ts, phase, level, message, json.dumps(data) if data is not None else None),
            )
            event_id = cursor.lastrowid
        return RunEvent(id=event_id, run_id=run_id, ts=ts, phase=phase, level=level, message=message, data=data)

    def list_events_for_run(self, run_id: str) -> list[RunEvent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY id ASC", (run_id,)).fetchall()
            return [self._row_to_event(row) for row in rows]

    def list_recent_events(self, limit: int = 100) -> list[RunEvent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM run_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_event(row) for row in reversed(rows)]

    # -- Autopilot ------------------------------------------------------------------------

    def upsert_autopilot_plan(
        self, plan_id: str, repository_id: int, owner_login: str, request: AutopilotPlanRequest
    ) -> AutopilotPlan:
        """One plan per repository -- (re)activating replaces the existing plan's settings
        (a fresh id only the first time) rather than creating a second one."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, created_at FROM autopilot_plans WHERE repository_id = ?", (repository_id,)
            ).fetchone()
            now = _now()
            row_id = existing["id"] if existing else plan_id
            created_at = existing["created_at"] if existing else now
            conn.execute(
                "INSERT INTO autopilot_plans (id, repository_id, owner_login, status, schedule_type, run_time, "
                "timezone, weekly_day, custom_days_json, max_runs_per_day, focus_areas_json, autonomy_level, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(repository_id) DO UPDATE SET "
                "status = excluded.status, schedule_type = excluded.schedule_type, run_time = excluded.run_time, "
                "timezone = excluded.timezone, weekly_day = excluded.weekly_day, "
                "custom_days_json = excluded.custom_days_json, max_runs_per_day = excluded.max_runs_per_day, "
                "focus_areas_json = excluded.focus_areas_json, autonomy_level = excluded.autonomy_level, "
                "updated_at = excluded.updated_at",
                (
                    row_id, repository_id, owner_login, AutopilotPlanStatus.active.value, request.schedule_type.value,
                    request.run_time, request.timezone, request.weekly_day, json.dumps(request.custom_days),
                    request.max_runs_per_day, json.dumps([f.value for f in request.focus_areas]),
                    request.autonomy_level.value, created_at, now,
                ),
            )
            return self._row_to_plan(
                conn.execute("SELECT * FROM autopilot_plans WHERE repository_id = ?", (repository_id,)).fetchone()
            )

    def get_autopilot_plan(self, repository_id: int) -> AutopilotPlan | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM autopilot_plans WHERE repository_id = ?", (repository_id,)).fetchone()
            return self._row_to_plan(row) if row else None

    def get_autopilot_plan_by_id(self, plan_id: str) -> AutopilotPlan | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM autopilot_plans WHERE id = ?", (plan_id,)).fetchone()
            return self._row_to_plan(row) if row else None

    def set_autopilot_plan_status(self, plan_id: str, status: AutopilotPlanStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE autopilot_plans SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _now(), plan_id),
            )

    def list_active_autopilot_plans(self) -> list[AutopilotPlan]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_plans WHERE status = ?", (AutopilotPlanStatus.active.value,)
            ).fetchall()
            return [self._row_to_plan(row) for row in rows]

    def create_scheduled_runs(self, plan_id: str, repository_id: int, scheduled_ats: list[str]) -> list[ScheduledRun]:
        with self._connect() as conn:
            created = []
            for scheduled_at in scheduled_ats:
                run_id = f"sr_{uuid.uuid4().hex}"
                conn.execute(
                    "INSERT INTO autopilot_scheduled_runs "
                    "(id, plan_id, repository_id, scheduled_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, plan_id, repository_id, scheduled_at, ScheduledRunStatus.scheduled.value, _now()),
                )
                created.append(run_id)
            if not created:
                return []
            rows = conn.execute(
                f"SELECT * FROM autopilot_scheduled_runs WHERE id IN ({','.join('?' * len(created))}) "
                "ORDER BY scheduled_at ASC",
                created,
            ).fetchall()
            return [self._row_to_scheduled_run(row) for row in rows]

    def cancel_upcoming_scheduled_runs(self, plan_id: str) -> None:
        """Cancels every not-yet-started run in a plan -- used when the whole plan is
        cancelled, or when its settings are replaced and the old upcoming slots no longer
        reflect what the user just configured."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE autopilot_scheduled_runs SET status = ? "
                "WHERE plan_id = ? AND status IN (?, ?)",
                (ScheduledRunStatus.cancelled.value, plan_id, ScheduledRunStatus.scheduled.value,
                 ScheduledRunStatus.waiting.value),
            )

    def get_scheduled_run(self, scheduled_run_id: str) -> ScheduledRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM autopilot_scheduled_runs WHERE id = ?", (scheduled_run_id,)
            ).fetchone()
            return self._row_to_scheduled_run(row) if row else None

    def update_scheduled_run(self, scheduled_run_id: str, **fields: object) -> None:
        if not fields:
            return
        if "status" in fields and isinstance(fields["status"], ScheduledRunStatus):
            fields["status"] = fields["status"].value
        unknown = set(fields) - _SCHEDULED_RUN_UPDATABLE_COLUMNS
        if unknown:
            raise ValueError(f"Cannot update unknown scheduled run column(s): {sorted(unknown)}")
        assignments = ", ".join(f"{column} = ?" for column in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE autopilot_scheduled_runs SET {assignments} WHERE id = ?",
                (*fields.values(), scheduled_run_id),
            )

    def list_due_scheduled_runs(self, now: str) -> list[ScheduledRun]:
        """Rows the scheduler tick should act on this pass: not yet started, and due."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_scheduled_runs WHERE status IN (?, ?) AND scheduled_at <= ? "
                "ORDER BY scheduled_at ASC",
                (ScheduledRunStatus.scheduled.value, ScheduledRunStatus.waiting.value, now),
            ).fetchall()
            return [self._row_to_scheduled_run(row) for row in rows]

    def list_in_flight_scheduled_runs(self) -> list[ScheduledRun]:
        """Rows the scheduler has started but whose underlying Run hasn't reached a terminal
        state yet -- reconciled against the real Run status each tick."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_scheduled_runs WHERE status = ? AND run_id IS NOT NULL",
                (ScheduledRunStatus.running.value,),
            ).fetchall()
            return [self._row_to_scheduled_run(row) for row in rows]

    def list_upcoming_scheduled_runs(self, repository_id: int) -> list[ScheduledRun]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_scheduled_runs WHERE repository_id = ? AND status IN (?, ?) "
                "ORDER BY scheduled_at ASC",
                (repository_id, ScheduledRunStatus.scheduled.value, ScheduledRunStatus.waiting.value),
            ).fetchall()
            return [self._row_to_scheduled_run(row) for row in rows]

    def list_recent_scheduled_runs(self, repository_id: int, limit: int = 10) -> list[ScheduledRun]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_scheduled_runs WHERE repository_id = ? "
                "AND status NOT IN (?, ?) ORDER BY scheduled_at DESC LIMIT ?",
                (repository_id, ScheduledRunStatus.scheduled.value, ScheduledRunStatus.waiting.value, limit),
            ).fetchall()
            return [self._row_to_scheduled_run(row) for row in rows]

    def count_scheduled_runs_started_today(self, plan_id: str, day_prefix: str) -> int:
        """day_prefix is an ISO date ('YYYY-MM-DD') -- counts runs from this plan that
        actually started (running or further) today, for the max-runs-per-day cap."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM autopilot_scheduled_runs "
                "WHERE plan_id = ? AND started_at IS NOT NULL AND started_at LIKE ?",
                (plan_id, f"{day_prefix}%"),
            ).fetchone()
            return int(row["n"])

    def has_active_run_for_repository(self, repository_id: int) -> bool:
        """Dedup guard: Autopilot must never start a second run for a repository that
        already has one queued/running, regardless of who/what started the first one."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM runs r JOIN tasks t ON t.id = r.task_id "
                "WHERE t.repository_id = ? AND r.status IN (?, ?) LIMIT 1",
                (repository_id, RunStatus.queued.value, RunStatus.running.value),
            ).fetchone()
            return row is not None

    # -- AI settings ------------------------------------------------------------------------
    # One row per user, replaced wholesale on every save -- there is deliberately no
    # per-operation override table: RepoPilot does not do multi-model routing, so "the
    # user's AI settings" is always exactly this one row.

    def upsert_user_ai_settings(
        self,
        owner_login: str,
        provider: AIProviderName,
        model: str,
        encrypted_api_key: str | None,
        endpoint: str | None,
        *,
        keep_existing_key: bool = False,
    ) -> UserAISettings:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT encrypted_api_key, created_at FROM user_ai_settings WHERE owner_login = ?", (owner_login,)
            ).fetchone()
            if keep_existing_key and existing is not None:
                encrypted_api_key = existing["encrypted_api_key"]
            now = _now()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                "INSERT INTO user_ai_settings "
                "(owner_login, provider, model, encrypted_api_key, endpoint, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?) "
                "ON CONFLICT(owner_login) DO UPDATE SET "
                "provider = excluded.provider, model = excluded.model, "
                "encrypted_api_key = excluded.encrypted_api_key, endpoint = excluded.endpoint, "
                "enabled = 1, updated_at = excluded.updated_at",
                (owner_login, provider.value, model, encrypted_api_key, endpoint, created_at, now),
            )
            return self._row_to_ai_settings(
                conn.execute("SELECT * FROM user_ai_settings WHERE owner_login = ?", (owner_login,)).fetchone()
            )

    def get_user_ai_settings(self, owner_login: str) -> UserAISettings | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM user_ai_settings WHERE owner_login = ?", (owner_login,)).fetchone()
            return self._row_to_ai_settings(row) if row else None

    @staticmethod
    def _row_to_ai_settings(row: sqlite3.Row) -> UserAISettings:
        return UserAISettings(
            owner_login=row["owner_login"],
            provider=AIProviderName(row["provider"]),
            model=row["model"],
            encrypted_api_key=row["encrypted_api_key"],
            endpoint=row["endpoint"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"],
            task_id=row["task_id"],
            status=RunStatus(row["status"]),
            triggered_by=row["triggered_by"],
            owner_login=row["owner_login"],
            branch_name=row["branch_name"],
            worktree_path=row["worktree_path"],
            base_branch=row["base_branch"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            pr_url=row["pr_url"],
            error_message=row["error_message"],
            commit_sha=row["commit_sha"],
            review_result=(ReviewResult(**json.loads(row["review_result_json"])) if row["review_result_json"] else None),
            test_results=(
                [TestOutcome(**item) for item in json.loads(row["test_results_json"])]
                if row["test_results_json"]
                else []
            ),
            ai_provider=row["ai_provider"],
            ai_model=row["ai_model"],
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RunEvent:
        return RunEvent(
            id=row["id"],
            run_id=row["run_id"],
            ts=row["ts"],
            phase=row["phase"],
            level=row["level"],
            message=row["message"],
            data=json.loads(row["data_json"]) if row["data_json"] else None,
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            repository_id=row["repository_id"],
            title=row["title"],
            description=row["description"],
            priority=row["priority"],
            risk=RiskLevel(row["risk"]),
            affected_files=json.loads(row["affected_files_json"]),
            required_checks=json.loads(row["required_checks_json"]),
            source=row["source"],
            requires_human_approval=bool(row["requires_human_approval"]),
            status=TaskStatus(row["status"]),
            approved_at=row["approved_at"],
        )

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> AutopilotPlan:
        return AutopilotPlan(
            id=row["id"],
            repository_id=row["repository_id"],
            owner_login=row["owner_login"],
            status=AutopilotPlanStatus(row["status"]),
            schedule_type=ScheduleType(row["schedule_type"]),
            run_time=row["run_time"],
            timezone=row["timezone"],
            weekly_day=row["weekly_day"],
            custom_days=json.loads(row["custom_days_json"]),
            max_runs_per_day=row["max_runs_per_day"],
            focus_areas=[FocusArea(f) for f in json.loads(row["focus_areas_json"])],
            autonomy_level=AutonomyLevel(row["autonomy_level"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_scheduled_run(row: sqlite3.Row) -> ScheduledRun:
        return ScheduledRun(
            id=row["id"],
            plan_id=row["plan_id"],
            repository_id=row["repository_id"],
            scheduled_at=row["scheduled_at"],
            status=ScheduledRunStatus(row["status"]),
            task_id=row["task_id"],
            run_id=row["run_id"],
            result_message=row["result_message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
