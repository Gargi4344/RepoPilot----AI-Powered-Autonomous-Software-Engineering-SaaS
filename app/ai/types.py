from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class AIMessage:
    """One turn in a provider-neutral conversation. `tool_call_id`/`name` are only
    populated for role="tool" messages (a tool's result being fed back to the model) --
    every provider adapter is responsible for translating this into whatever shape its own
    API expects (e.g. Anthropic's tool_result content blocks, Ollama's {"role": "tool"})."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    # Only set on an assistant message that made tool call(s) -- carries them forward so the
    # next turn's request can show the model its own prior calls in conversation history.
    tool_calls: list[ToolCall] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """A callable tool RepoPilot exposes to the model, in the OpenAI/Ollama function-calling
    shape -- the shape every existing TOOLS list in this codebase was already written in.
    Provider adapters translate this into their own tool-schema format."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


FinishReason = Literal["stop", "tool_calls", "malformed_tool_call", "length", "error"]


@dataclass(frozen=True)
class AIRequest:
    """RepoPilot's own provider-independent representation of one model call. Every agent
    (backlog, commit message, review, coding) builds one of these and hands it to whichever
    AIProvider is active -- it never constructs a provider-specific payload itself."""

    messages: list[AIMessage]
    system_prompt: str | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    json_mode: bool = False  # ask for a single JSON object back, no prose -- used by the
    # backlog/review/commit-message agents, never by the coding agent (which uses tools).
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class AIResponse:
    """Normalized reply from any provider. RepoPilot agents only ever read this shape --
    never a raw Ollama dict, google.genai response, or Anthropic Message object."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    finish_reason: FinishReason = "stop"
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    tool_calling: bool
    json_mode: bool
    lists_models: bool  # whether list_models() can actually enumerate available models


class ConnectionStatus(str, Enum):
    ok = "ok"
    error = "error"


@dataclass(frozen=True)
class ConnectionTestResult:
    status: ConnectionStatus
    message: str


# -- Normalized error hierarchy ------------------------------------------------------------
# Every provider adapter is responsible for catching its own SDK's exceptions and re-raising
# one of these, so nothing above the adapter (agents, orchestrator, API endpoints) ever needs
# to know what a real ollama.ResponseError or anthropic.APIStatusError looks like.


class AIProviderError(RuntimeError):
    """Base class for every normalized AI-provider failure. Safe to show str(exc) to a user
    -- provider adapters must never let a raw API key or secret reach this message."""


class ConfigurationError(AIProviderError):
    """The requested provider/model isn't supported, or required configuration (an API key,
    a usable endpoint) is missing -- this is a setup problem, not a runtime one."""


class AuthenticationError(AIProviderError):
    """The provider rejected the credentials (bad/expired/revoked API key)."""


class ProviderUnavailableError(AIProviderError):
    """The provider couldn't be reached at all (connection refused, DNS failure, timeout
    establishing the connection) -- e.g. Ollama not running, or a cloud deployment trying to
    reach a `localhost` endpoint that only exists on the user's own machine."""


class ModelUnavailableError(AIProviderError):
    """The endpoint was reachable but the requested model isn't available there."""


class RateLimitedError(AIProviderError):
    """The provider is throttling this request; safe to retry later."""


class AITimeoutError(AIProviderError):
    """The request did not complete within the provider's own timeout."""


class NetworkError(AIProviderError):
    """A network failure other than "unavailable at all" (e.g. dropped mid-request)."""


class UnsupportedCapabilityError(AIProviderError):
    """The selected model/provider cannot support something RepoPilot's agents need (tool
    calling, in practice) -- surfaced before a long agent run starts, not mid-run."""
