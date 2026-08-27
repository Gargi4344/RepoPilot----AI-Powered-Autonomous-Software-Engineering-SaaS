import dataclasses

import pytest

from app.ai.factory import build_provider, resolve_provider, validate_model_choice
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.types import ConfigurationError
from app.config import Settings
from app.models import AIProviderName, UserAISettings


def _settings(**overrides) -> Settings:
    base = Settings.from_environment()
    return dataclasses.replace(base, **overrides)


def _user_settings(**overrides) -> UserAISettings:
    defaults = {
        "owner_login": "octocat",
        "provider": AIProviderName.ollama,
        "model": "qwen2.5-coder:7b",
        "encrypted_api_key": None,
        "endpoint": None,
        "enabled": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return UserAISettings(**defaults)


def test_resolve_provider_falls_back_to_legacy_settings_when_user_has_none() -> None:
    provider = resolve_provider(None, _settings(llm_provider="ollama", ollama_model="m", ollama_host="http://x:1"))

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "m"
    assert provider.host == "http://x:1"


def test_resolve_provider_falls_back_to_legacy_gemini_settings() -> None:
    provider = resolve_provider(None, _settings(llm_provider="gemini", gemini_model="g", gemini_api_key="key"))

    assert isinstance(provider, GeminiProvider)
    assert provider.model == "g"


def test_resolve_provider_falls_back_when_user_settings_disabled() -> None:
    user_settings = _user_settings(enabled=False, provider=AIProviderName.anthropic, model="claude-sonnet-5")

    provider = resolve_provider(user_settings, _settings(llm_provider="ollama", ollama_model="m"))

    assert isinstance(provider, OllamaProvider)


def test_resolve_provider_selects_ollama_with_the_users_endpoint() -> None:
    user_settings = _user_settings(endpoint="http://my-ollama:11434", model="llama3")

    provider = resolve_provider(user_settings, _settings())

    assert isinstance(provider, OllamaProvider)
    assert provider.host == "http://my-ollama:11434"
    assert provider.model == "llama3"


def test_resolve_provider_selects_anthropic_and_decrypts_the_key() -> None:
    from app.ai.crypto import encrypt_secret

    encrypted = encrypt_secret("sk-real-key", "test-secret")
    user_settings = _user_settings(
        provider=AIProviderName.anthropic, model="claude-sonnet-5", encrypted_api_key=encrypted
    )

    provider = resolve_provider(user_settings, _settings(ai_encryption_key="test-secret"))

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet-5"


def test_resolve_provider_raises_a_clear_error_when_the_stored_key_cannot_be_decrypted() -> None:
    from app.ai.crypto import encrypt_secret

    encrypted = encrypt_secret("sk-real-key", "secret-a")
    user_settings = _user_settings(provider=AIProviderName.anthropic, model="claude-sonnet-5", encrypted_api_key=encrypted)

    with pytest.raises(ConfigurationError, match="could not be read"):
        resolve_provider(user_settings, _settings(ai_encryption_key="secret-b"))


def test_build_provider_rejects_an_unknown_model_for_a_curated_provider() -> None:
    with pytest.raises(ConfigurationError, match="does not support a capability"):
        build_provider(AIProviderName.anthropic, "gpt-4", api_key="x")


def test_build_provider_accepts_any_model_name_for_ollama() -> None:
    provider = build_provider(AIProviderName.ollama, "whatever-someone-pulled-locally", endpoint="http://x:1")
    assert provider.model == "whatever-someone-pulled-locally"


def test_validate_model_choice_rejects_empty_model() -> None:
    with pytest.raises(ConfigurationError):
        validate_model_choice(AIProviderName.ollama, "")


def test_validate_model_choice_accepts_a_known_anthropic_model() -> None:
    validate_model_choice(AIProviderName.anthropic, "claude-sonnet-5")  # must not raise
