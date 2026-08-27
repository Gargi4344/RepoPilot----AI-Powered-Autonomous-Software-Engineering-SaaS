import asyncio
import dataclasses
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app


def _init_repo_with_passing_tests(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (path / "tests").mkdir()
    (path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _init_repo_with_pre_existing_ruff_failure(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (path / "tests").mkdir()
    (path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    # Unused import -- ruff flags this by default (F401), unrelated to any task the coding
    # agent will be asked to do.
    (path / "unrelated.py").write_text("import os\n\n\ndef unused():\n    pass\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _no_tool_response(content: str) -> dict:
    return {"message": {"role": "assistant", "content": content, "tool_calls": None}}


def _tool_call_response(name: str, arguments: dict) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    }


def _mock_coding_agent_writes_readme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stands in for the local Ollama model: writes README.md, stops, then answers the
    commit-message prompt. app.agents.coding_agent and app.agents.commit_message both
    `import ollama` -- it's the same module object in both, so patching it must be done
    once, in one place, with responses queued in the exact order the pipeline calls it:
    (1) coding agent's tool call, (2) coding agent's final no-tool-calls turn, (3) the
    commit-message JSON call. Patching per-module would silently overwrite itself."""
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("write_file", {"path": "README.md", "content": "# Demo\n"}),
            _no_tool_response("Added a README."),
            {"message": {"content": '{"type": "docs", "scope": "", "subject": "add a README"}'}},
        ]
    )

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return await chat(**kwargs)

    monkeypatch.setattr("ollama.AsyncClient", FakeClient)


def test_start_run_completes_the_full_pipeline_and_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)

    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]  # README task, since tests already exist and there are no TODOs
    client.post(f"/api/v1/tasks/{task_id}/approve")

    start = client.post(f"/api/v1/tasks/{task_id}/runs")
    assert start.status_code == 202
    run_id = start.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "needs_human_review"
    assert run["branch_name"].startswith("pr-engineer/")
    assert run["commit_sha"] is not None
    assert any(result["tool"] == "pytest" and result["exit_code"] == 0 for result in run["test_results"])

    task_after = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task_after["status"] == "needs_human_review"

    events = client.get(f"/api/v1/runs/{run_id}/events").json()
    phases = {event["phase"] for event in events}
    assert {"setup", "worktree", "coding", "test", "commit", "complete"}.issubset(phases)


def test_start_run_pushes_and_opens_a_draft_pr_when_allowlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("write_file", {"path": "README.md", "content": "# Demo\n"}),
            _no_tool_response("Added a README."),
            {"message": {"content": '{"type": "docs", "scope": "", "subject": "add a README"}'}},
            {
                "message": {
                    "content": '{"approved": true, "summary": "Looks good.", '
                    '"concerns": [], "risk": "low"}'
                }
            },
        ]
    )

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return await chat(**kwargs)

    monkeypatch.setattr("ollama.AsyncClient", FakeClient)

    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/testowner/testrepo.git"], cwd=repo, check=True
    )

    # Settings is a frozen dataclass built once at app-startup from the environment; a test
    # can't change ALLOWED_TARGET_REPOS/GITHUB_TOKEN via env vars after that, so override the
    # already-constructed orchestrator's settings instance directly for this test only.
    monkeypatch.setattr(
        main_module.orchestrator,
        "_settings",
        dataclasses.replace(
            main_module.orchestrator._settings,
            allowed_target_repos=["testowner/testrepo"],
            github_token="fake-github-token",
        ),
    )

    pushed = {}

    def fake_push(worktree_path, branch_name, token=None):
        pushed["worktree_path"] = worktree_path
        pushed["branch_name"] = branch_name
        pushed["token"] = token

    async def fake_open_pr(repo_slug, branch_name, base_branch, title, body, token):
        return {"html_url": "https://github.com/testowner/testrepo/pull/7", "number": 7}

    monkeypatch.setattr("app.orchestrator.push", fake_push)
    monkeypatch.setattr("app.orchestrator.open_draft_pull_request", fake_open_pr)

    client = TestClient(app)
    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")

    # Calling submit() directly with no github_token exercises the static
    # GITHUB_TOKEN/ALLOWED_TARGET_REPOS path specifically -- the API's start_run endpoint
    # always passes the logged-in user's own token instead (covered by
    # test_run_starters_own_token_bypasses_the_static_allowlist).
    run_id = main_module.orchestrator.submit(task_id)
    asyncio.run(main_module.orchestrator.execute(run_id))

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "pr_open"
    assert run["pr_url"] == "https://github.com/testowner/testrepo/pull/7"
    assert run["review_result"]["approved"] is True
    assert run["review_result"]["risk"] == "low"

    task_after = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task_after["status"] == "pr_open"

    assert pushed["branch_name"] == run["branch_name"]
    assert pushed["token"] == "fake-github-token"

    events = client.get(f"/api/v1/runs/{run_id}/events").json()
    phases = {event["phase"] for event in events}
    assert {"review", "pr"}.issubset(phases)


def test_start_run_ignores_pre_existing_failures_unrelated_to_the_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A repo-wide ruff failure that exists before the coding agent touches anything (and
    # that the task never asked it to fix) must not block the run -- only a check that was
    # passing at baseline and got broken by the change counts as a blocker.
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_pre_existing_ruff_failure(repo)
    client = TestClient(app)

    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")

    start = client.post(f"/api/v1/tasks/{task_id}/runs")
    run_id = start.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "needs_human_review"
    assert run["commit_sha"] is not None
    assert any(r["tool"] == "ruff" and r["exit_code"] != 0 for r in run["test_results"])
    assert any(r["tool"] == "pytest" and r["exit_code"] == 0 for r in run["test_results"])

    task_after = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task_after["status"] == "needs_human_review"

    events = client.get(f"/api/v1/runs/{run_id}/events").json()
    assert any(e["phase"] == "baseline" and "ruff" in e["message"] for e in events)


def test_run_starters_own_token_bypasses_the_static_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A repo picked via the GitHub repo list is never on ALLOWED_TARGET_REPOS -- the
    # run-starter's own OAuth token (passed to submit()) must still be able to push and
    # open a PR for it, using GitHub's own permissions on that token as the real boundary.
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/someone/their-repo.git"], cwd=repo, check=True
    )
    monkeypatch.setattr(
        main_module.orchestrator,
        "_settings",
        dataclasses.replace(main_module.orchestrator._settings, allowed_target_repos=[]),  # deliberately empty
    )

    pushed = {}

    def fake_push(worktree_path, branch_name, token=None):
        pushed["token"] = token

    async def fake_open_pr(repo_slug, branch_name, base_branch, title, body, token):
        pushed["open_pr_token"] = token
        return {"html_url": "https://github.com/someone/their-repo/pull/1", "number": 1}

    monkeypatch.setattr("app.orchestrator.push", fake_push)
    monkeypatch.setattr("app.orchestrator.open_draft_pull_request", fake_open_pr)

    client = TestClient(app)
    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")

    run_id = main_module.orchestrator.submit(task_id, github_token="the-run-starters-oauth-token")
    asyncio.run(main_module.orchestrator.execute(run_id))

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "pr_open"
    assert pushed["token"] == "the-run-starters-oauth-token"
    assert pushed["open_pr_token"] == "the-run-starters-oauth-token"
    # The token is discarded once used -- never lingers for a run that's already finished.
    assert run_id not in main_module.orchestrator._pending_push_tokens


def test_cancel_stops_an_in_progress_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The coding agent's model call hangs until explicitly released, so this proves
    # cancel() actually interrupts in-flight work rather than just flipping a status flag
    # after the pipeline would have finished anyway. reached_chat lets the test wait until
    # execution has genuinely reached that point (past baseline tests/worktree setup,
    # whatever real wall-clock time those take) instead of guessing at a sleep duration.
    reached_chat = asyncio.Event()
    release_forever = asyncio.Event()  # never set -- chat() hangs until the task is cancelled

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            reached_chat.set()
            await release_forever.wait()
            raise AssertionError("should have been cancelled before chat() returned")

    monkeypatch.setattr("ollama.AsyncClient", FakeClient)

    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)
    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")

    async def run_and_cancel() -> str:
        run_id = main_module.orchestrator.submit(task_id)
        task = asyncio.create_task(main_module.orchestrator.execute(run_id))
        await asyncio.wait_for(reached_chat.wait(), timeout=15)

        assert main_module.orchestrator.cancel(run_id) is True

        done, _pending = await asyncio.wait([task], timeout=15)
        assert task in done
        assert task.cancelled()
        return run_id

    run_id = asyncio.run(run_and_cancel())

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "cancelled"
    task_after = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task_after["status"] == "cancelled"

    events = client.get(f"/api/v1/runs/{run_id}/events").json()
    assert any(e["phase"] == "cancelled" for e in events)


def test_cancel_returns_false_when_run_is_not_active() -> None:
    assert main_module.orchestrator.cancel("no-such-run") is False


def test_cancel_endpoint_for_missing_run_returns_404() -> None:
    response = TestClient(app).post("/api/v1/runs/does-not-exist/cancel")

    assert response.status_code == 404


def test_cancel_endpoint_for_a_finished_run_returns_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)
    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")
    start = client.post(f"/api/v1/tasks/{task_id}/runs")
    run_id = start.json()["id"]

    response = client.post(f"/api/v1/runs/{run_id}/cancel")

    assert response.status_code == 409


def test_start_run_requires_approval(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)
    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]

    response = client.post(f"/api/v1/tasks/{task_id}/runs")

    assert response.status_code == 409


def test_start_run_for_missing_task_returns_404() -> None:
    response = TestClient(app).post("/api/v1/tasks/does-not-exist/runs")

    assert response.status_code == 404


def test_status_endpoint_reports_concurrency_limit() -> None:
    response = TestClient(app).get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["max_concurrent_runs"] == 2


def test_run_always_records_which_ai_provider_and_model_it_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Whatever AI configuration actually resolves for this user (their own saved settings,
    # or -- absent those -- the deployment's environment-configured default), the run must
    # record it, so activity history is never blank about what was used. This deliberately
    # doesn't assert a specific value (other tests in this module and test_ai_settings_api.py
    # share the same test-user identity against a shared DB and may have saved their own AI
    # settings first), only that a snapshot was captured at all.
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)

    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")
    start = client.post(f"/api/v1/tasks/{task_id}/runs")
    run_id = start.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["ai_provider"]
    assert run["ai_model"]


def test_run_uses_the_users_own_configured_ai_provider_over_the_legacy_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_coding_agent_writes_readme(monkeypatch)
    repo = tmp_path / "repo"
    _init_repo_with_passing_tests(repo)
    client = TestClient(app)

    saved = client.put(
        "/api/v1/ai-settings",
        json={"provider": "ollama", "model": "a-users-own-custom-model", "endpoint": "http://custom-host:1"},
    )
    assert saved.status_code == 200

    analyze = client.post("/api/v1/repositories/analyze", json={"path": str(repo)})
    task_id = analyze.json()["tasks"][0]["id"]
    client.post(f"/api/v1/tasks/{task_id}/approve")
    start = client.post(f"/api/v1/tasks/{task_id}/runs")
    run_id = start.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["ai_provider"] == "ollama"
    assert run["ai_model"] == "a-users-own-custom-model"
