import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_get_ai_settings_before_configuration_returns_null(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    response = client.get("/api/v1/ai-settings")

    assert response.status_code == 200
    assert response.json() is None


def test_save_ai_settings_never_returns_the_api_key() -> None:
    client = TestClient(app)

    response = client.put(
        "/api/v1/ai-settings",
        json={"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-super-secret-value"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "api_key" not in body
    assert "sk-super-secret-value" not in response.text
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-sonnet-5"
    assert body["configured"] is True


def test_save_ai_settings_rejects_an_unsupported_model() -> None:
    client = TestClient(app)

    response = client.put(
        "/api/v1/ai-settings", json={"provider": "anthropic", "model": "not-a-real-model", "api_key": "sk-x"}
    )

    assert response.status_code == 422


def test_save_ai_settings_without_a_key_keeps_the_previously_saved_one() -> None:
    client = TestClient(app)
    client.put("/api/v1/ai-settings", json={"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-x"})

    response = client.put("/api/v1/ai-settings", json={"provider": "anthropic", "model": "claude-opus-5"})

    assert response.status_code == 200
    assert response.json()["model"] == "claude-opus-5"
    assert response.json()["configured"] is True


def test_get_ai_settings_after_saving_reflects_the_saved_configuration() -> None:
    client = TestClient(app)
    client.put("/api/v1/ai-settings", json={"provider": "ollama", "model": "qwen2.5-coder:7b", "endpoint": "http://x:1"})

    response = client.get("/api/v1/ai-settings")

    body = response.json()
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["endpoint"] == "http://x:1"
    assert "api_key" not in body


def test_test_connection_reports_a_clear_failure_for_an_unreachable_ollama_endpoint() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/ai-settings/test-connection",
        json={"provider": "ollama", "model": "qwen2.5-coder:7b", "endpoint": "http://127.0.0.1:1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["message"]


def test_test_connection_succeeds_when_the_provider_confirms_a_healthy_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model="qwen2.5-coder:7b")])

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    client = TestClient(app)

    response = client.post(
        "/api/v1/ai-settings/test-connection",
        json={"provider": "ollama", "model": "qwen2.5-coder:7b", "endpoint": "http://localhost:11434"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Connected successfully."}


def test_test_connection_rejects_an_unsupported_model_without_making_a_network_call() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/ai-settings/test-connection", json={"provider": "anthropic", "model": "not-a-real-model"}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_list_ollama_models_reports_a_clear_error_when_unreachable() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/ai-settings/ollama-models", params={"endpoint": "http://127.0.0.1:1"})

    assert response.status_code == 503


def test_list_ollama_models_returns_the_live_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model="qwen2.5-coder:7b"), SimpleNamespace(model="llama3")])

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    client = TestClient(app)

    response = client.get("/api/v1/ai-settings/ollama-models")

    assert response.status_code == 200
    assert response.json() == ["qwen2.5-coder:7b", "llama3"]


def test_ai_settings_require_authentication() -> None:
    from app.auth import SessionUser
    from app.main import get_current_user

    client = TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.get("/api/v1/ai-settings")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: SessionUser(
            login="test-user", name="Test User", avatar_url=None, access_token="test-access-token"
        )
