from __future__ import annotations

import anthropic

from app.ai.base import AIProvider
from app.ai.types import (
    AIProviderError,
    AIRequest,
    AIResponse,
    AITimeoutError,
    AuthenticationError,
    ConfigurationError,
    ConnectionStatus,
    ConnectionTestResult,
    ModelUnavailableError,
    NetworkError,
    ProviderCapabilities,
    RateLimitedError,
    TokenUsage,
    ToolCall,
)
from app.models import AIProviderName

DEFAULT_MAX_TOKENS = 4096

# Only models confirmed compatible with this app's tool-calling coding agent loop --
# RepoPilot never lets a user pick an arbitrary Anthropic model string.
KNOWN_MODELS = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-8",
    "claude-opus-4-7",
]


def _to_anthropic_tools(request: AIRequest) -> list[dict] | anthropic.NotGiven:
    if not request.tools:
        return anthropic.NOT_GIVEN
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in request.tools]


def _to_anthropic_messages(request: AIRequest) -> list[dict]:
    messages: list[dict] = []
    tool_result_buffer: list[dict] = []

    def flush() -> None:
        if tool_result_buffer:
            messages.append({"role": "user", "content": list(tool_result_buffer)})
            tool_result_buffer.clear()

    for m in request.messages:
        if m.role == "tool":
            tool_result_buffer.append({"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content})
            continue
        flush()
        if m.role == "user":
            messages.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            content: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
            for call in m.tool_calls or []:
                content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
            messages.append({"role": "assistant", "content": content or [{"type": "text", "text": " "}]})
    flush()
    return messages


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        if not api_key:
            raise ConfigurationError("An API key is required to use Anthropic.")
        self._api_key = api_key
        self.model = model
        self.provider_name = AIProviderName.anthropic

    def _client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(api_key=self._api_key)

    async def chat(self, request: AIRequest) -> AIResponse:
        # Anthropic has no hard API-level JSON-mode toggle (unlike Ollama's format="json" or
        # Gemini's response_mime_type) -- the calling agents already instruct this strictly
        # in their own system prompts, but reinforcing it here costs nothing and reduces the
        # chance of a stray sentence around the JSON object.
        system_prompt = request.system_prompt or ""
        if request.json_mode:
            system_prompt = (system_prompt + "\n\nRespond with ONLY the JSON object -- no prose, no markdown fences.").strip()
        try:
            response = await self._client().messages.create(
                model=self.model,
                max_tokens=request.max_tokens or DEFAULT_MAX_TOKENS,
                system=system_prompt or anthropic.NOT_GIVEN,
                messages=_to_anthropic_messages(request),
                tools=_to_anthropic_tools(request),
                temperature=request.temperature if request.temperature is not None else anthropic.NOT_GIVEN,
            )
        except anthropic.AuthenticationError as exc:
            raise AuthenticationError("Anthropic rejected the configured API key.") from exc
        except anthropic.NotFoundError as exc:
            raise ModelUnavailableError(f'Model "{self.model}" is not available on Anthropic.') from exc
        except anthropic.RateLimitError as exc:
            raise RateLimitedError("Anthropic rate limit reached -- try again shortly.") from exc
        except anthropic.APITimeoutError as exc:
            raise AITimeoutError("Anthropic did not respond in time.") from exc
        except anthropic.APIConnectionError as exc:
            raise NetworkError("Could not reach Anthropic -- check network connectivity.") from exc
        except anthropic.APIStatusError as exc:
            raise AIProviderError(f"Anthropic request failed: {exc.message}") from exc

        text_parts = [b.text for b in response.content if b.type == "text"]
        tool_calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input)) for b in response.content if b.type == "tool_use"
        ]
        finish_reason = "tool_calls" if tool_calls else ("length" if response.stop_reason == "max_tokens" else "stop")
        usage = TokenUsage(input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
        return AIResponse(
            text="".join(text_parts).strip(),
            tool_calls=tool_calls,
            model=self.model,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def test_connection(self) -> ConnectionTestResult:
        try:
            await self._client().messages.create(
                model=self.model, max_tokens=8, messages=[{"role": "user", "content": "ping"}]
            )
        except anthropic.AuthenticationError:
            return ConnectionTestResult(status=ConnectionStatus.error, message="Invalid Anthropic API key.")
        except anthropic.NotFoundError:
            return ConnectionTestResult(
                status=ConnectionStatus.error, message=f'Model "{self.model}" is not available on Anthropic.'
            )
        except anthropic.RateLimitError:
            return ConnectionTestResult(status=ConnectionStatus.error, message="Anthropic rate limit reached.")
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            return ConnectionTestResult(status=ConnectionStatus.error, message="Could not reach Anthropic.")
        except anthropic.APIStatusError as exc:
            return ConnectionTestResult(status=ConnectionStatus.error, message=f"Anthropic request failed: {exc.message}")
        return ConnectionTestResult(status=ConnectionStatus.ok, message="Connected successfully.")

    async def list_models(self) -> list[str] | None:
        return None  # no live discovery -- KNOWN_MODELS is the selectable list in the UI

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tool_calling=True, json_mode=False, lists_models=False)
