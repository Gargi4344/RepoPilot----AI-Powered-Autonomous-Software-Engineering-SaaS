"""The single place responsible for turning "which provider/model is configured" into a
live AIProvider instance. Nothing else in the codebase should contain an
`if provider == "ollama"` branch -- that conditional belongs here, exactly once."""

from __future__ import annotations

from app.ai.base import AIProvider
from app.ai.crypto import decrypt_secret
from app.ai.providers.anthropic_provider import KNOWN_MODELS as ANTHROPIC_MODELS
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.gemini_provider import KNOWN_MODELS as GEMINI_MODELS
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.types import ConfigurationError
from app.config import Settings
from app.models import AIProviderName, UserAISettings

SUPPORTED_PROVIDERS = {AIProviderName.ollama, AIProviderName.anthropic, AIProviderName.gemini}

# Providers with a fixed, curated model list -- a user can only select a model RepoPilot has
# confirmed works with its tool-calling coding agent. Ollama has no such list: any locally
# pulled model name is accepted, since the set of what's pulled is inherently per-deployment.
KNOWN_MODELS_BY_PROVIDER: dict[AIProviderName, list[str]] = {
    AIProviderName.anthropic: ANTHROPIC_MODELS,
    AIProviderName.gemini: GEMINI_MODELS,
}


def validate_model_choice(provider: AIProviderName, model: str) -> None:
    """Rejects an unsupported provider or a model RepoPilot hasn't confirmed compatible,
    before any settings are saved or a run is started -- not mid-run."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigurationError(f'"{provider}" is not a supported AI provider.')
    if not model or not model.strip():
        raise ConfigurationError("A model must be selected.")
    known = KNOWN_MODELS_BY_PROVIDER.get(provider)
    if known is not None and model not in known:
        raise ConfigurationError(
            f'The selected model does not support a capability required by RepoPilot. '
            f'"{model}" is not one of the models confirmed compatible for {provider.value}: {", ".join(known)}.'
        )


def _construct(
    provider: AIProviderName, model: str, *, api_key: str | None = None, endpoint: str | None = None
) -> AIProvider:
    if provider == AIProviderName.ollama:
        return OllamaProvider(host=endpoint or "", model=model)
    if provider == AIProviderName.anthropic:
        return AnthropicProvider(api_key=api_key, model=model)
    return GeminiProvider(api_key=api_key, model=model)  # gemini -- the only remaining supported provider


def build_provider(
    provider: AIProviderName, model: str, *, api_key: str | None = None, endpoint: str | None = None
) -> AIProvider:
    """Constructs a provider adapter directly from already-resolved settings (no DB lookup,
    no decryption) -- used both by resolve_provider below and by the Test Connection
    endpoint, which needs to build a provider from values that may not be saved yet. Model
    compatibility is validated here -- this is the path a user's own saved AI settings go
    through."""
    validate_model_choice(provider, model)
    return _construct(provider, model, api_key=api_key, endpoint=endpoint)


def legacy_provider(settings: Settings) -> AIProvider:
    """The pre-per-user-settings global provider, from environment configuration -- the
    fallback for a user who hasn't configured (or has disabled) their own AI settings, so
    existing single-tenant/dev deployments keep working exactly as before. Deliberately
    skips validate_model_choice: an operator's existing LLM_PROVIDER/*_MODEL configuration
    must keep working unconditionally, even a model string set before this curated-list
    check existed."""
    if settings.llm_provider == "gemini":
        return _construct(AIProviderName.gemini, settings.gemini_model, api_key=settings.gemini_api_key)
    return _construct(AIProviderName.ollama, settings.ollama_model, endpoint=settings.ollama_host)


def resolve_provider(user_settings: UserAISettings | None, settings: Settings) -> AIProvider:
    """The one place that turns "this user's configuration" into a live provider. Falls back
    to the deployment's legacy environment-configured provider when the user has no settings
    of their own yet, or has disabled them -- see legacy_provider above."""
    if user_settings is None or not user_settings.enabled:
        return legacy_provider(settings)

    api_key: str | None = None
    if user_settings.encrypted_api_key:
        api_key = decrypt_secret(user_settings.encrypted_api_key, settings.ai_encryption_key)
        if api_key is None:
            raise ConfigurationError(
                "Your stored AI provider credentials could not be read -- please reconfigure your AI settings."
            )

    return build_provider(user_settings.provider, user_settings.model, api_key=api_key, endpoint=user_settings.endpoint)
