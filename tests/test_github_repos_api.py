import dataclasses
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.models import GitHubRepo


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "app.py").write_text("# TODO: write tests\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_list_github_repos_returns_the_users_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_user_repos(token: str) -> list[GitHubRepo]:
        assert token == "test-access-token"  # matches conftest.py's overridden SessionUser
        return [
            GitHubRepo(
                name="demo",
                full_name="octocat/demo",
                description=None,
                html_url="https://github.com/octocat/demo",
                clone_url="https://github.com/octocat/demo.git",
                default_branch="main",
                private=False,
                fork=False,
                updated_at="2026-08-01T00:00:00Z",
            )
        ]

    monkeypatch.setattr(main_module, "list_user_repos", fake_list_user_repos)

    response = TestClient(main_module.app).get("/api/v1/github/repos")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "demo",
            "full_name": "octocat/demo",
            "description": None,
            "html_url": "https://github.com/octocat/demo",
            "clone_url": "https://github.com/octocat/demo.git",
            "default_branch": "main",
            "private": False,
            "fork": False,
            "updated_at": "2026-08-01T00:00:00Z",
        }
    ]


def test_start_github_repo_clones_and_analyzes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source-repo"
    _init_repo(source)
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, workspace_root=tmp_path / "workspace")
    )
    # clone_repository takes a URL, but git clones a local path just as well -- avoids a
    # real network call while still exercising the real clone/analyze code path.
    real_clone_repository = main_module.clone_repository
    monkeypatch.setattr(
        main_module,
        "clone_repository",
        lambda clone_url, dest: real_clone_repository(str(source), dest),
    )

    response = TestClient(main_module.app).post("/api/v1/github/repos/octocat/demo/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository_id"] is not None
    assert any(task["source"] == "repository-todo" for task in payload["tasks"])

    # Calling it again should pull (not re-clone) the already-cloned repo.
    response_again = TestClient(main_module.app).post("/api/v1/github/repos/octocat/demo/start")
    assert response_again.status_code == 200
