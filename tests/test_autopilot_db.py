from pathlib import Path

import pytest

from app.db import Database
from app.models import (
    AutonomyLevel,
    AutopilotPlanRequest,
    AutopilotPlanStatus,
    FocusArea,
    RunStatus,
    ScheduledRunStatus,
    ScheduleType,
)


def _request(**overrides) -> AutopilotPlanRequest:
    defaults = {
        "schedule_type": ScheduleType.daily,
        "run_time": "09:00",
        "timezone": "UTC",
        "focus_areas": [FocusArea.bug_fixes, FocusArea.tests],
        "autonomy_level": AutonomyLevel.balanced,
    }
    defaults.update(overrides)
    return AutopilotPlanRequest(**defaults)


def _repo(db: Database, tmp_path: Path) -> int:
    return db.upsert_repository(str(tmp_path), "octocat")


def test_upsert_autopilot_plan_creates_then_replaces_settings(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)

    created = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    assert created.status == AutopilotPlanStatus.active
    assert created.autonomy_level == AutonomyLevel.balanced

    updated = db.upsert_autopilot_plan(
        "plan-2", repository_id, "octocat", _request(autonomy_level=AutonomyLevel.conservative)
    )

    # Same repository -> same plan row (id unchanged), settings replaced.
    assert updated.id == created.id
    assert updated.autonomy_level == AutonomyLevel.conservative
    assert db.get_autopilot_plan(repository_id).id == created.id


def test_get_autopilot_plan_returns_none_when_never_configured(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    assert db.get_autopilot_plan(repository_id) is None


def test_set_autopilot_plan_status_pause_and_resume(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())

    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.paused)
    assert db.get_autopilot_plan(repository_id).status == AutopilotPlanStatus.paused

    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.active)
    assert db.get_autopilot_plan(repository_id).status == AutopilotPlanStatus.active


def test_list_active_autopilot_plans_excludes_paused_and_cancelled(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    r1 = db.upsert_repository(str(tmp_path / "a"), "octocat")
    r2 = db.upsert_repository(str(tmp_path / "b"), "octocat")
    r3 = db.upsert_repository(str(tmp_path / "c"), "octocat")
    active_plan = db.upsert_autopilot_plan("p1", r1, "octocat", _request())
    paused_plan = db.upsert_autopilot_plan("p2", r2, "octocat", _request())
    db.upsert_autopilot_plan("p3", r3, "octocat", _request())
    db.set_autopilot_plan_status(paused_plan.id, AutopilotPlanStatus.paused)
    db.set_autopilot_plan_status(db.get_autopilot_plan(r3).id, AutopilotPlanStatus.cancelled)

    active = db.list_active_autopilot_plans()

    assert [p.id for p in active] == [active_plan.id]


def test_create_and_list_scheduled_runs(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())

    created = db.create_scheduled_runs(
        plan.id, repository_id, ["2026-01-06T09:00:00+00:00", "2026-01-07T09:00:00+00:00"]
    )

    assert len(created) == 2
    assert all(sr.status == ScheduledRunStatus.scheduled for sr in created)
    upcoming = db.list_upcoming_scheduled_runs(repository_id)
    assert [sr.scheduled_at for sr in upcoming] == ["2026-01-06T09:00:00+00:00", "2026-01-07T09:00:00+00:00"]


def test_cancel_upcoming_scheduled_runs_only_touches_not_yet_started(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    created = db.create_scheduled_runs(plan.id, repository_id, ["2026-01-06T09:00:00+00:00", "2026-01-07T09:00:00+00:00"])
    db.update_scheduled_run(created[0].id, status=ScheduledRunStatus.completed, finished_at="x")

    db.cancel_upcoming_scheduled_runs(plan.id)

    first = db.get_scheduled_run(created[0].id)
    second = db.get_scheduled_run(created[1].id)
    assert first.status == ScheduledRunStatus.completed  # untouched history
    assert second.status == ScheduledRunStatus.cancelled  # was still 'scheduled'


def test_update_scheduled_run_rejects_unknown_column(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    created = db.create_scheduled_runs(plan.id, repository_id, ["2026-01-06T09:00:00+00:00"])

    with pytest.raises(ValueError, match="unknown scheduled run column"):
        db.update_scheduled_run(created[0].id, not_a_real_column="x")


def test_list_due_scheduled_runs_only_returns_scheduled_and_waiting_that_are_due(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    plan = db.upsert_autopilot_plan("plan-1", repository_id, "octocat", _request())
    due, _future = db.create_scheduled_runs(
        plan.id, repository_id, ["2026-01-01T09:00:00+00:00", "2099-01-01T09:00:00+00:00"]
    )
    db.update_scheduled_run(due.id, status=ScheduledRunStatus.waiting)

    result = db.list_due_scheduled_runs("2026-06-01T00:00:00+00:00")

    assert [sr.id for sr in result] == [due.id]


def test_has_active_run_for_repository(tmp_path: Path) -> None:
    from app.models import ProjectAnalysis, RiskLevel, Task

    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    analysis = ProjectAnalysis(
        root=str(tmp_path), languages={}, manifests=[], readme_present=False, test_directories=[],
        todo_items=[], source_files=0, ignored_files=0, detected_tools=[], summary="",
    )
    analysis_id = db.insert_analysis(repository_id, analysis)
    task = Task(id="t1", title="x", description="y", priority=3, risk=RiskLevel.low, source="repository-todo")
    db.sync_backlog_tasks(repository_id, analysis_id, [task])

    assert db.has_active_run_for_repository(repository_id) is False

    db.approve_task("t1")
    db.create_run("run-1", "t1")

    assert db.has_active_run_for_repository(repository_id) is True

    db.update_run("run-1", status=RunStatus.pr_open, finished_at="x")

    assert db.has_active_run_for_repository(repository_id) is False


def test_create_run_persists_triggered_by(tmp_path: Path) -> None:
    from app.models import ProjectAnalysis, RiskLevel, Task

    db = Database(tmp_path / "test.db")
    repository_id = _repo(db, tmp_path)
    analysis = ProjectAnalysis(
        root=str(tmp_path), languages={}, manifests=[], readme_present=False, test_directories=[],
        todo_items=[], source_files=0, ignored_files=0, detected_tools=[], summary="",
    )
    analysis_id = db.insert_analysis(repository_id, analysis)
    task = Task(id="t1", title="x", description="y", priority=3, risk=RiskLevel.low, source="repository-todo")
    db.sync_backlog_tasks(repository_id, analysis_id, [task])
    db.approve_task("t1")

    db.create_run("run-1", "t1", triggered_by="autopilot")

    assert db.get_run("run-1").triggered_by == "autopilot"
