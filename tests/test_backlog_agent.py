import asyncio
from pathlib import Path

import pytest

from app.agents.backlog_agent import generate_tasks
from app.ai.providers.ollama_provider import OllamaProvider
from app.models import ProjectAnalysis, RiskLevel


def _analysis(root: str) -> ProjectAnalysis:
    return ProjectAnalysis(
        root=root, languages={"Python": 3}, manifests=["pyproject.toml"], readme_present=True,
        test_directories=["tests"], todo_items=[], source_files=3, ignored_files=0,
        detected_tools=["pytest", "ruff"], summary="3 supported source files.",
    )


def _provider() -> OllamaProvider:
    return OllamaProvider(host="http://localhost:11434", model="m")


def _patch_chat(monkeypatch: pytest.MonkeyPatch, content: str | None, raise_exc: Exception | None = None) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            if raise_exc:
                raise raise_exc
            return {"message": {"content": content}}

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)


def test_generate_tasks_parses_valid_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("# Demo\n")
    _patch_chat(
        monkeypatch,
        '{"tasks": [{"title": "Add input validation", "description": "Validate query params '
        'in the search handler.", "priority": 4, "risk": "medium", "affected_files": ["src/search.py"]}]}',
    )

    tasks = asyncio.run(generate_tasks(tmp_path, _analysis(str(tmp_path)), ai_provider=_provider()))

    assert len(tasks) == 1
    task = tasks[0]
    assert task.title == "Add input validation"
    assert task.priority == 4
    assert task.risk == RiskLevel.medium
    assert task.affected_files == ["src/search.py"]
    assert task.source == "llm-backlog"
    assert task.status == "backlog"
    assert task.requires_human_approval is True


def test_generate_tasks_caps_at_max_and_skips_invalid_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposals = [{"title": f"Task {i}", "description": "Do something useful here."} for i in range(10)]
    proposals.insert(2, {"title": "", "description": "missing title should be dropped"})
    proposals.insert(3, {"description": "missing title key entirely"})
    _patch_chat(monkeypatch, __import__("json").dumps({"tasks": proposals}))

    tasks = asyncio.run(generate_tasks(tmp_path, _analysis(str(tmp_path)), ai_provider=_provider()))

    assert 0 < len(tasks) <= 6
    assert all(t.title for t in tasks)


def test_generate_tasks_falls_back_to_empty_on_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_chat(monkeypatch, "not json")

    tasks = asyncio.run(generate_tasks(tmp_path, _analysis(str(tmp_path)), ai_provider=_provider()))

    assert tasks == []


def test_generate_tasks_falls_back_to_empty_on_connection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_chat(monkeypatch, None, raise_exc=ConnectionError("no ollama"))

    tasks = asyncio.run(generate_tasks(tmp_path, _analysis(str(tmp_path)), ai_provider=_provider()))

    assert tasks == []


def test_generate_tasks_clamps_out_of_range_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chat(
        monkeypatch,
        '{"tasks": [{"title": "X", "description": "Y", "priority": 99, "risk": "bogus"}]}',
    )

    tasks = asyncio.run(generate_tasks(tmp_path, _analysis(str(tmp_path)), ai_provider=_provider()))

    assert tasks[0].priority == 5
    assert tasks[0].risk == RiskLevel.low
