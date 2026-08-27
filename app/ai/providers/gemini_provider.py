from __future__ import annotations

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.ai.base import AIProvider
from app.ai.types import (
    AIProviderError,
    AIRequest,
    AIResponse,
    AuthenticationError,
    ConfigurationError,
    ConnectionStatus,
    ConnectionTestResult,
    ModelUnavailableError,
    ProviderCapabilities,
    RateLimitedError,
    ToolCall,
)
from app.models import AIProviderName

# A small, curated set known to work well with this app's tool-calling coding agent --
# Gemini's full model catalog includes many variants (vision-only, embeddings, etc.) that
# aren't valid choices here, so this isn't fetched live the way Ollama's is.
KNOWN_MODELS = ["gemini-3.5-flash", "gemini-3-pro", "gemini-2.5-flash", "gemini-2.5-pro"]


def _to_gemini_tool(request: AIRequest) -> genai_types.Tool | None:
    if not request.tools:
        return None
    return genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
            for t in request.tools
        ]
    )


def _to_gemini_contents(request: AIRequest) -> list[genai_types.Content]:
    contents: list[genai_types.Content] = []
    for m in request.messages:
        if m.role == "user":
            contents.append(genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=m.content)]))
        elif m.role == "assistant":
            parts = [genai_types.Part.from_text(text=m.content)] if m.content else []
            for call in m.tool_calls or []:
                parts.append(genai_types.Part.from_function_call(name=call.name, args=call.arguments))
            contents.append(genai_types.Content(role="model", parts=parts))
        elif m.role == "tool":
            contents.append(
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_function_response(name=m.name or "", response={"result": m.content})],
                )
            )
    return contents


def _raise_normalized(exc: genai_errors.APIError) -> None:
    if exc.code in (401, 403):
        raise AuthenticationError("Gemini rejected the configured API key.") from exc
    if exc.code == 404:
        raise ModelUnavailableError(f'Model "{exc}" is not available.') from exc
    if exc.code == 429:
        raise RateLimitedError("Gemini rate limit reached -- try again shortly.") from exc
    raise AIProviderError(f"Gemini request failed: {exc}") from exc


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        if not api_key:
            raise ConfigurationError("An API key is required to use Gemini.")
        self._api_key = api_key
        self.model = model
        self.provider_name = AIProviderName.gemini

    def _client(self) -> genai.Client:
        return genai.Client(api_key=self._api_key)

    async def chat(self, request: AIRequest) -> AIResponse:
        config = genai_types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            tools=[t] if (t := _to_gemini_tool(request)) else None,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True) if request.tools else None,
            response_mime_type="application/json" if request.json_mode else None,
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
        )
        try:
            response = await self._client().aio.models.generate_content(
                model=self.model, contents=_to_gemini_contents(request), config=config
            )
        except genai_errors.APIError as exc:
            _raise_normalized(exc)

        function_calls = response.function_calls or []
        if function_calls:
            tool_calls = [
                ToolCall(id=f"call_{i}", name=c.name or "", arguments=dict(c.args or {}))
                for i, c in enumerate(function_calls)
            ]
            return AIResponse(text=response.text or "", tool_calls=tool_calls, model=self.model, finish_reason="tool_calls")
        return AIResponse(text=(response.text or "").strip(), model=self.model, finish_reason="stop")

    async def test_connection(self) -> ConnectionTestResult:
        try:
            await self._client().aio.models.generate_content(model=self.model, contents="ping")
        except genai_errors.APIError as exc:
            try:
                _raise_normalized(exc)
            except AIProviderError as normalized:
                return ConnectionTestResult(status=ConnectionStatus.error, message=str(normalized))
        except Exception as exc:  # noqa: BLE001 -- this exists specifically to report any failure to the user
            return ConnectionTestResult(status=ConnectionStatus.error, message=f"Could not reach Gemini: {exc}")
        return ConnectionTestResult(status=ConnectionStatus.ok, message="Connected successfully.")

    async def list_models(self) -> list[str] | None:
        return None  # no live discovery -- KNOWN_MODELS is the selectable list in the UI

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tool_calling=True, json_mode=True, lists_models=False)
