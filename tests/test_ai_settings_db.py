from pathlib import Path

from app.db import Database
from app.models import AIProviderName, ProjectAnalysis, RiskLevel, Task


def test_get_user_ai_settings_returns_none_when_never_configured(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    assert db.get_user_ai_settings("octocat") is None


def test_upsert_user_ai_settings_creates_then_replaces(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")

    created = db.upsert_user_ai_settings("octocat", AIProviderName.ollama, "qwen2.5-coder:7b", None, "http://x:1")
    assert created.provider == AIProviderName.ollama
    assert created.model == "qwen2.5-coder:7b"
    assert created.enabled is True

    updated = db.upsert_user_ai_settings(
        "octocat", AIProviderName.anthropic, "claude-sonnet-5", "encrypted-blob", None
    )
    assert updated.provider == AIProviderName.anthropic
    assert updated.model == "claude-sonnet-5"
    assert updated.encrypted_api_key == "encrypted-blob"

    assert db.get_user_ai_settings("octocat").provider == AIProviderName.anthropic


def test_upsert_user_ai_settings_keeps_existing_key_when_requested(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.upsert_user_ai_settings("octocat", AIProviderName.anthropic, "claude-sonnet-5", "original-key", None)

    updated = db.upsert_user_ai_settings(
        "octocat", AIProviderName.anthropic, "claude-opus-5", None, None, keep_existing_key=True
    )

    assert updated.model == "claude-opus-5"
    assert updated.encrypted_api_key == "original-key"


def test_user_ai_settings_are_scoped_per_owner(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.upsert_user_ai_settings("octocat", AIProviderName.ollama, "m1", None, None)
    db.upsert_user_ai_settings("other-user", AIProviderName.gemini, "m2", "key", None)

    assert db.get_user_ai_settings("octocat").provider == AIProviderName.ollama
    assert db.get_user_ai_settings("other-user").provider == AIProviderName.gemini


def _seed_approved_task(db: Database, tmp_path: Path, task_id: str = "t1") -> None:
    repository_id = db.upsert_repository(str(tmp_path), "octocat")
    analysis = ProjectAnalysis(
        root=str(tmp_path), languages={}, manifests=[], readme_present=False, test_directories=[],
        todo_items=[], source_files=0, ignored_files=0, detected_tools=[], summary="",
    )
    analysis_id = db.insert_analysis(repository_id, analysis)
    task = Task(id=task_id, title="x", description="y", priority=3, risk=RiskLevel.low, source="repository-todo")
    db.sync_backlog_tasks(repository_id, analysis_id, [task])
    db.approve_task(task_id)


def test_create_run_persists_owner_login_and_ai_snapshot(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    _seed_approved_task(db, tmp_path)

    db.create_run("run-1", "t1", owner_login="octocat", ai_provider="anthropic", ai_model="claude-sonnet-5")

    run = db.get_run("run-1")
    assert run.owner_login == "octocat"
    assert run.ai_provider == "anthropic"
    assert run.ai_model == "claude-sonnet-5"


def test_update_run_can_set_ai_snapshot_after_creation(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    _seed_approved_task(db, tmp_path)
    db.create_run("run-1", "t1")

    db.update_run("run-1", ai_provider="ollama", ai_model="qwen2.5-coder:7b")

    run = db.get_run("run-1")
    assert run.ai_provider == "ollama"
    assert run.ai_model == "qwen2.5-coder:7b"
