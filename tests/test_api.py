from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_current_mode() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "phase-2-human-gated-execution"}


def test_analyze_endpoint_returns_low_risk_tasks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("# TODO: write tests\n")

    response = TestClient(app).post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["languages"] == {"Python": 1}
    assert all(task["risk"] == "low" for task in payload["tasks"])
    assert all(task["requires_human_approval"] for task in payload["tasks"])
    assert all(task["status"] == "backlog" for task in payload["tasks"])
    assert payload["repository_id"] is not None


def test_analyze_endpoint_persists_repository_and_tasks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("# TODO: persist me\n")
    client = TestClient(app)

    analyze_response = client.post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})
    repository_id = analyze_response.json()["repository_id"]

    repositories = client.get("/api/v1/repositories").json()
    assert any(repo["id"] == repository_id for repo in repositories)

    tasks = client.get(f"/api/v1/repositories/{repository_id}/tasks").json()
    assert tasks
    task_id = tasks[0]["id"]

    task_detail = client.get(f"/api/v1/tasks/{task_id}")
    assert task_detail.status_code == 200
    assert task_detail.json()["status"] == "backlog"


def test_approve_task_transitions_status_and_guards_reapproval(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("# TODO: approve me\n")
    client = TestClient(app)
    analyze_response = client.post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})
    task_id = analyze_response.json()["tasks"][0]["id"]

    approve_response = client.post(f"/api/v1/tasks/{task_id}/approve")
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    second_attempt = client.post(f"/api/v1/tasks/{task_id}/approve")
    assert second_attempt.status_code == 409

    missing = client.post("/api/v1/tasks/does-not-exist/approve")
    assert missing.status_code == 404


def test_generate_tasks_adds_llm_proposed_tasks_to_the_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Demo\n")
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
    client = TestClient(app)
    analyze_response = client.post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})
    repository_id = analyze_response.json()["repository_id"]
    baseline_task_count = len(analyze_response.json()["tasks"])

    chat = AsyncMock(
        return_value={
            "message": {
                "content": '{"tasks": [{"title": "Add type hints", "description": '
                '"Add type hints to add() for clarity.", "priority": 3, "risk": "low", '
                '"affected_files": ["app.py"]}]}'
            }
        }
    )

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return await chat(**kwargs)

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)

    response = client.post(f"/api/v1/repositories/{repository_id}/generate-tasks")

    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == baseline_task_count + 1
    llm_tasks = [t for t in tasks if t["source"] == "llm-backlog"]
    assert len(llm_tasks) == 1
    assert llm_tasks[0]["title"] == "Add type hints"
    assert llm_tasks[0]["status"] == "backlog"
    assert llm_tasks[0]["requires_human_approval"] is True


def test_get_repository_analysis_returns_the_latest_analysis(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("# TODO: analyze me\n")
    client = TestClient(app)
    analyze_response = client.post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})
    repository_id = analyze_response.json()["repository_id"]

    response = client.get(f"/api/v1/repositories/{repository_id}/analysis")

    assert response.status_code == 200
    assert response.json()["languages"] == {"Python": 1}


def test_get_repository_analysis_for_missing_repository_returns_404() -> None:
    response = TestClient(app).get("/api/v1/repositories/999999/analysis")

    assert response.status_code == 404


def test_generate_tasks_for_missing_repository_returns_404() -> None:
    response = TestClient(app).post("/api/v1/repositories/999999/generate-tasks")

    assert response.status_code == 404
