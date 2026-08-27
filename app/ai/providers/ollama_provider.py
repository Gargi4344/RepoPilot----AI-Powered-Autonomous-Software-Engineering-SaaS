from __future__ import annotations

import httpx
import ollama

from app.ai.base import AIProvider
from app.ai.text_tool_calls import (
    extract_embedded_tool_calls,
    extract_fallback_tool_calls,
    looks_like_unparsed_tool_call,
)
from app.ai.types import (
    AIProviderError,
    AIRequest,
    AIResponse,
    ConnectionStatus,
    ConnectionTestResult,
    ModelUnavailableError,
    ProviderCapabilities,
    ProviderUnavailableError,
    ToolCall,
)
from app.models import AIProviderName

DEFAULT_HOST = "http://localhost:11434"


def _to_ollama_messages(request: AIRequest) -> list[dict]:
    messages: list[dict] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    for m in request.messages:
        if m.role == "assistant" and m.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": m.content,
                    "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls],
                }
            )
        else:
            messages.append({"role": m.role, "content": m.content})
    return messages


def _to_ollama_tools(request: AIRequest) -> list[dict] | None:
    if not request.tools:
        return None
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in request.tools
    ]


class OllamaProvider(AIProvider):
    """Talks to a local (or self-hosted remote) Ollama server. Owns the recovery heuristics
    for models that don't reliably populate the native tool_calls field -- see
    app.ai.text_tool_calls for why that's specifically an Ollama/local-model concern, not a
    general one every provider needs."""

    def __init__(self, host: str, model: str) -> None:
        self.host = host or DEFAULT_HOST
        self.model = model
        self.provider_name = AIProviderName.ollama

    def _client(self) -> ollama.AsyncClient:
        return ollama.AsyncClient(host=self.host)

    async def chat(self, request: AIRequest) -> AIResponse:
        try:
            response = await self._client().chat(
                model=self.model,
                messages=_to_ollama_messages(request),
                tools=_to_ollama_tools(request),
                format="json" if request.json_mode else None,
            )
        except (httpx.ConnectError, ConnectionRefusedError, ConnectionError) as exc:
            raise ProviderUnavailableError(
                f"Could not reach Ollama at {self.host}. Is Ollama running and is this endpoint correct?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"Timed out connecting to Ollama at {self.host}.") from exc
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                raise ModelUnavailableError(
                    f'Model "{self.model}" is not available on this Ollama server. '
                    f"Pull it first (ollama pull {self.model}) or choose a different model."
                ) from exc
            raise AIProviderError(f"Ollama request failed: {exc}") from exc

        message = response["message"]
        content = message.get("content") or ""

        native_calls = message.get("tool_calls") or []
        flat_calls: list[dict] = [
            {"name": c["function"]["name"], "arguments": c["function"].get("arguments") or {}} for c in native_calls
        ]
        if not flat_calls and request.tools:
            # Native tool_calls came back empty -- the model may have written the call as
            # plain text instead (see app.ai.text_tool_calls for why this only ever happens
            # with local models like qwen2.5-coder).
            flat_calls = extract_fallback_tool_calls(content) or extract_embedded_tool_calls(content)

        if flat_calls:
            tool_calls = [ToolCall(id=f"call_{i}", name=c["name"], arguments=c["arguments"]) for i, c in enumerate(flat_calls)]
            return AIResponse(text=content, tool_calls=tool_calls, model=self.model, finish_reason="tool_calls")

        if request.tools and looks_like_unparsed_tool_call(content):
            return AIResponse(text=content, model=self.model, finish_reason="malformed_tool_call")

        return AIResponse(text=content.strip(), model=self.model, finish_reason="stop")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            models = await self.list_models()
        except ProviderUnavailableError as exc:
            return ConnectionTestResult(status=ConnectionStatus.error, message=str(exc))
        if models is not None and self.model not in models:
            return ConnectionTestResult(
                status=ConnectionStatus.error,
                message=f'Connected to Ollama, but model "{self.model}" is not pulled there yet.',
            )
        return ConnectionTestResult(status=ConnectionStatus.ok, message="Connected successfully.")

    async def list_models(self) -> list[str] | None:
        try:
            response = await self._client().list()
        except (httpx.ConnectError, ConnectionRefusedError, ConnectionError) as exc:
            raise ProviderUnavailableError(
                f"Could not reach Ollama at {self.host}. Is Ollama running and is this endpoint correct?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"Timed out connecting to Ollama at {self.host}.") from exc
        return [m.model for m in response.models if m.model]

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tool_calling=True, json_mode=True, lists_models=True)
