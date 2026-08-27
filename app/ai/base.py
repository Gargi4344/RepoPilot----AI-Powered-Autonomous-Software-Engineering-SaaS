from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.types import AIRequest, AIResponse, ConnectionTestResult, ProviderCapabilities
from app.models import AIProviderName


class AIProvider(ABC):
    """The normalized interface every RepoPilot agent (backlog, commit message, review,
    coding) talks to. Nothing above this layer ever imports ollama/anthropic/google.genai
    directly, constructs a provider-specific request, or reads a provider-specific response
    -- that isolation is the entire point of this abstraction."""

    #: The model name this instance was configured with -- exposed so callers can record it
    #: on a run's snapshot without needing provider-specific introspection.
    model: str
    #: Which provider this is, e.g. for labeling a run's recorded AI configuration.
    provider_name: AIProviderName

    @abstractmethod
    async def chat(self, request: AIRequest) -> AIResponse:
        """Sends one normalized request and returns one normalized response. Raises a
        subclass of AIProviderError (never a raw SDK exception) on failure."""

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """A lightweight, side-effect-free check that this provider is reachable and the
        configured credentials/model are usable. Never raises -- failures are reported
        through the returned result, since this exists specifically to be shown to a user
        who is still setting up their configuration."""

    @abstractmethod
    async def list_models(self) -> list[str] | None:
        """Enumerates models actually available at this provider/endpoint, or None if this
        provider doesn't support live model discovery (the caller should fall back to a
        fixed, known-compatible list in that case)."""

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Static capability flags for this provider -- used to validate a model selection
        against what RepoPilot's agents actually require before a run starts."""
