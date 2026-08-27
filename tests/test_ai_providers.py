import asyncio
from types import SimpleNamespace

import pytest

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.types import (
    AIMessage,
    AIRequest,
    AuthenticationError,
    ConfigurationError,
    ConnectionStatus,
    ModelUnavailableError,
    ProviderUnavailableError,
    RateLimitedError,
    ToolDefinition,
)
from app.models import AIProviderName

# -- OllamaProvider ----------------------------------------------------------------------


def _patch_ollama_chat(monkeypatch: pytest.MonkeyPatch, response: dict) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return response

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)


def test_ollama_provider_normalizes_a_plain_text_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ollama_chat(monkeypatch, {"message": {"content": "Hello there."}})
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))

    assert response.text == "Hello there."
    assert response.tool_calls == []
    assert response.finish_reason == "stop"
    assert response.model == "qwen"
    assert provider.provider_name == AIProviderName.ollama


def test_ollama_provider_normalizes_native_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ollama_chat(
        monkeypatch,
        {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "list_files", "arguments": {"path": "."}}}],
            }
        },
    )
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")
    tools = [ToolDefinition(name="list_files", description="d", parameters={})]

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")], tools=tools)))

    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "list_files"
    assert response.tool_calls[0].arguments == {"path": "."}


def test_ollama_provider_recovers_a_tool_call_written_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ollama_chat(
        monkeypatch,
        {"message": {"content": '{"name": "list_files", "arguments": {"path": "."}}', "tool_calls": None}},
    )
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")
    tools = [ToolDefinition(name="list_files", description="d", parameters={})]

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")], tools=tools)))

    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].name == "list_files"


def test_ollama_provider_reports_malformed_tool_call_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ollama_chat(monkeypatch, {"message": {"content": "{invalid json", "tool_calls": None}})
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")
    tools = [ToolDefinition(name="list_files", description="d", parameters={})]

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")], tools=tools)))

    assert response.finish_reason == "malformed_tool_call"


def test_ollama_provider_raises_provider_unavailable_when_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            raise ConnectionError("refused")

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))


def test_ollama_provider_raises_model_unavailable_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    import ollama

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            raise ollama.ResponseError("model not found", 404)

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    provider = OllamaProvider(host="http://localhost:11434", model="does-not-exist")

    with pytest.raises(ModelUnavailableError):
        asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))


def test_ollama_provider_lists_models(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model="qwen2.5-coder:7b"), SimpleNamespace(model="llama3")])

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    provider = OllamaProvider(host="http://localhost:11434", model="qwen2.5-coder:7b")

    models = asyncio.run(provider.list_models())

    assert models == ["qwen2.5-coder:7b", "llama3"]


def test_ollama_provider_test_connection_reports_unreachable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def list(self):
            raise ConnectionRefusedError()

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    provider = OllamaProvider(host="http://localhost:11434", model="qwen")

    result = asyncio.run(provider.test_connection())

    assert result.status == ConnectionStatus.error
    assert "ollama" in result.message.lower()


def test_ollama_provider_test_connection_flags_a_model_not_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model="llama3")])

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    provider = OllamaProvider(host="http://localhost:11434", model="qwen2.5-coder:7b")

    result = asyncio.run(provider.test_connection())

    assert result.status == ConnectionStatus.error
    assert "not pulled" in result.message.lower()


# -- GeminiProvider -----------------------------------------------------------------------


def test_gemini_provider_requires_an_api_key() -> None:
    with pytest.raises(ConfigurationError):
        GeminiProvider(api_key=None, model="gemini-3.5-flash")


def test_gemini_provider_normalizes_a_text_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_generate_content(*, model, contents, config):
        return SimpleNamespace(text="Hello.", function_calls=[])

    class FakeModels:
        generate_content = staticmethod(_fake_generate_content)

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("app.ai.providers.gemini_provider.genai.Client", FakeClient)
    provider = GeminiProvider(api_key="fake-key", model="gemini-3.5-flash")

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))

    assert response.text == "Hello."
    assert response.finish_reason == "stop"


def test_gemini_provider_normalizes_a_function_call(monkeypatch: pytest.MonkeyPatch) -> None:
    call = SimpleNamespace(name="list_files", args={"path": "."})

    async def _fake_generate_content(*, model, contents, config):
        return SimpleNamespace(text="", function_calls=[call])

    class FakeModels:
        generate_content = staticmethod(_fake_generate_content)

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("app.ai.providers.gemini_provider.genai.Client", FakeClient)
    provider = GeminiProvider(api_key="fake-key", model="gemini-3.5-flash")
    tools = [ToolDefinition(name="list_files", description="d", parameters={})]

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")], tools=tools)))

    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].name == "list_files"
    assert response.tool_calls[0].arguments == {"path": "."}


def test_gemini_provider_normalizes_an_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.genai import errors as genai_errors

    async def _fake_generate_content(*, model, contents, config):
        raise genai_errors.ClientError(401, {"error": {"message": "bad key"}})

    class FakeModels:
        generate_content = staticmethod(_fake_generate_content)

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr("app.ai.providers.gemini_provider.genai.Client", FakeClient)
    provider = GeminiProvider(api_key="bad-key", model="gemini-3.5-flash")

    with pytest.raises(AuthenticationError):
        asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))


# -- AnthropicProvider --------------------------------------------------------------------


def test_anthropic_provider_requires_an_api_key() -> None:
    with pytest.raises(ConfigurationError):
        AnthropicProvider(api_key=None, model="claude-sonnet-5")


def test_anthropic_provider_normalizes_a_text_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Hello.")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )

    class FakeMessages:
        async def create(self, **kwargs):
            return message

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr("app.ai.providers.anthropic_provider.anthropic.AsyncAnthropic", FakeClient)
    provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-5")

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))

    assert response.text == "Hello."
    assert response.finish_reason == "stop"
    assert response.usage.input_tokens == 10


def test_anthropic_provider_normalizes_a_tool_use_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    message = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="call_1", name="list_files", input={"path": "."})],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )

    class FakeMessages:
        async def create(self, **kwargs):
            return message

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr("app.ai.providers.anthropic_provider.anthropic.AsyncAnthropic", FakeClient)
    provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-5")
    tools = [ToolDefinition(name="list_files", description="d", parameters={})]

    response = asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")], tools=tools)))

    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].name == "list_files"
    assert response.tool_calls[0].arguments == {"path": "."}


def _fake_httpx_response(status_code: int):
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code, request=request)


def test_anthropic_provider_normalizes_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    class FakeMessages:
        async def create(self, **kwargs):
            raise anthropic.AuthenticationError(
                message="invalid api key", response=_fake_httpx_response(401), body=None
            )

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr("app.ai.providers.anthropic_provider.anthropic.AsyncAnthropic", FakeClient)
    provider = AnthropicProvider(api_key="bad-key", model="claude-sonnet-5")

    with pytest.raises(AuthenticationError):
        asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))


def test_anthropic_provider_normalizes_rate_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    class FakeMessages:
        async def create(self, **kwargs):
            raise anthropic.RateLimitError(message="rate limited", response=_fake_httpx_response(429), body=None)

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr("app.ai.providers.anthropic_provider.anthropic.AsyncAnthropic", FakeClient)
    provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-5")

    with pytest.raises(RateLimitedError):
        asyncio.run(provider.chat(AIRequest(messages=[AIMessage(role="user", content="hi")])))
