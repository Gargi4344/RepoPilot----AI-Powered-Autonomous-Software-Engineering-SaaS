import asyncio

import pytest

from app.agents.review_agent import review_diff
from app.ai.providers.ollama_provider import OllamaProvider
from app.models import RiskLevel, Task


def _task() -> Task:
    return Task(
        id="task-1", title="Fix bug", description="Fix the bug", priority=3,
        risk=RiskLevel.low, source="repository-todo",
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


def test_review_diff_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chat(
        monkeypatch,
        '{"approved": true, "summary": "Looks fine.", "concerns": ["minor naming"], "risk": "low"}',
    )

    result = asyncio.run(review_diff(_task(), "diff --git a/x", ai_provider=_provider()))

    assert result.approved is True
    assert result.summary == "Looks fine."
    assert result.concerns == ["minor naming"]
    assert result.risk == RiskLevel.low


def test_review_diff_falls_back_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chat(monkeypatch, "not valid json at all")

    result = asyncio.run(review_diff(_task(), "diff --git a/x", ai_provider=_provider()))

    assert result.approved is False
    assert "unavailable" in result.summary.lower()


def test_review_diff_falls_back_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chat(monkeypatch, None, raise_exc=ConnectionError("no ollama"))

    result = asyncio.run(review_diff(_task(), "diff --git a/x", ai_provider=_provider()))

    assert result.approved is False
    assert result.risk == RiskLevel.medium


def test_review_diff_falls_back_on_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_chat(monkeypatch, '{"summary": "missing approved field"}')

    result = asyncio.run(review_diff(_task(), "diff --git a/x", ai_provider=_provider()))

    assert result.approved is False
    assert "unavailable" in result.summary.lower()
