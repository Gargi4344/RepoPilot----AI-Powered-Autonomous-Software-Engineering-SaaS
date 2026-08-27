from pathlib import Path

import pytest

from app.db import Database
from app.models import RiskLevel, Task, TaskStatus
from app.repository import RepositoryAnalyzer


def _task(task_id: str = "task-1") -> Task:
    return Task(
        id=task_id, title="Do the thing", description="Do the thing well",
        priority=3, risk=RiskLevel.low, source="repository-todo",
    )


def test_repository_and_task_round_trip(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")

    repository_id = db.upsert_repository("/repo/path", "user1")
    assert db.upsert_repository("/repo/path", "user1") == repository_id  # idempotent

    analysis = RepositoryAnalyzer().analyze(_git_repo(tmp_path))
    analysis_id = db.insert_analysis(repository_id, analysis)

    db.sync_backlog_tasks(repository_id, analysis_id, [_task()])
    tasks = db.list_tasks_for_repository(repository_id)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.backlog

    fetched = db.get_task("task-1")
    assert fetched is not None
    assert fetched.title == "Do the thing"
    assert db.get_task("missing") is None


def test_list_repositories_is_scoped_per_owner(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.upsert_repository("/repo/mine", "user1")
    db.upsert_repository("/repo/theirs", "user2")

    assert [r.path for r in db.list_repositories("user1")] == ["/repo/mine"]
    assert [r.path for r in db.list_repositories("user2")] == ["/repo/theirs"]
    assert db.list_repositories("user3") == []


def test_upsert_repository_shared_path_is_visible_to_each_owner_who_analyzed_it(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = db.upsert_repository("/repo/shared", "user1")
    assert db.upsert_repository("/repo/shared", "user2") == repository_id  # same row, new access grant

    assert [r.path for r in db.list_repositories("user1")] == ["/repo/shared"]
    assert [r.path for r in db.list_repositories("user2")] == ["/repo/shared"]
    assert db.user_can_access_repository(repository_id, "user1") is True
    assert db.user_can_access_repository(repository_id, "user2") is True
    assert db.user_can_access_repository(repository_id, "user3") is False


def test_sync_backlog_tasks_does_not_reset_approved_tasks(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = db.upsert_repository("/repo/path", "user1")
    analysis = RepositoryAnalyzer().analyze(_git_repo(tmp_path))
    analysis_id = db.insert_analysis(repository_id, analysis)

    db.sync_backlog_tasks(repository_id, analysis_id, [_task()])
    db.approve_task("task-1")

    db.sync_backlog_tasks(repository_id, analysis_id, [_task()])  # re-analyze with same task

    task = db.get_task("task-1")
    assert task is not None
    assert task.status == TaskStatus.approved


def test_approve_task_transitions_and_guards(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repository_id = db.upsert_repository("/repo/path", "user1")
    analysis = RepositoryAnalyzer().analyze(_git_repo(tmp_path))
    analysis_id = db.insert_analysis(repository_id, analysis)
    db.sync_backlog_tasks(repository_id, analysis_id, [_task()])

    approved = db.approve_task("task-1")
    assert approved is not None
    assert approved.status == TaskStatus.approved
    assert approved.approved_at is not None

    with pytest.raises(ValueError, match="not in backlog status"):
        db.approve_task("task-1")

    assert db.approve_task("missing") is None


def test_reconcile_orphaned_runs_fails_stuck_queued_and_running_rows(tmp_path: Path) -> None:
    # A run only ever advances via the in-process async task that started it -- if that
    # process crashed or was restarted, the row is stuck forever unless something cleans it
    # up. This is the exact bug observed in production: a run left at "running" for hours
    # after an earlier backend restart, permanently inflating the active-run count.
    db = Database(tmp_path / "test.db")
    repository_id = db.upsert_repository("/repo/path", "user1")
    analysis = RepositoryAnalyzer().analyze(_git_repo(tmp_path))
    analysis_id = db.insert_analysis(repository_id, analysis)
    db.sync_backlog_tasks(repository_id, analysis_id, [_task("task-1"), _task("task-2")])
    db.set_task_status("task-1", TaskStatus.running)
    db.set_task_status("task-2", TaskStatus.running)

    db.create_run("run-running", "task-1")
    db.update_run("run-running", status="running")
    db.create_run("run-queued", "task-2")  # create_run already inserts as queued
    db.create_run("run-finished", "task-1")
    db.update_run("run-finished", status="pr_open")  # already terminal -- must be left alone

    reconciled = db.reconcile_orphaned_runs()

    assert set(reconciled) == {"run-running", "run-queued"}
    assert db.get_run("run-running").status.value == "failed"
    assert db.get_run("run-running").error_message == "Run was interrupted by a server restart"
    assert db.get_run("run-queued").status.value == "failed"
    assert db.get_run("run-finished").status.value == "pr_open"  # untouched
    assert db.get_task("task-1").status == TaskStatus.failed
    assert db.get_task("task-2").status == TaskStatus.failed
    assert db.count_active_runs() == {}

    # Idempotent -- calling again with nothing left to reconcile is a no-op.
    assert db.reconcile_orphaned_runs() == []


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    return repo
