# AI Provider Architecture

RepoPilot's agent code never talks to Ollama, Anthropic, or Gemini directly. It talks to a
normalized `AIProvider` interface; a factory resolves which concrete provider that is per user,
per operation. This document explains that architecture, how to configure each provider, and
how to add a new one.

## One active provider/model per user

Each user configures exactly one AI provider and one model, under **Profile menu → AI Model**
(`/settings`). That single configuration is used for *every* AI operation of theirs:

- Repository analysis's task proposals (`generate_tasks`)
- The coding agent (`CodingAgent`)
- Commit message generation (`generate_commit_message`)
- Advisory code review (`review_diff`)

There is no per-operation override and no multi-model routing. If a user hasn't configured
anything (or has disabled their settings), RepoPilot falls back to the deployment's
environment-configured default (`LLM_PROVIDER`/`OLLAMA_*`/`GEMINI_*` in `.env`) — this is what
keeps existing single-tenant/dev deployments working unchanged.

## The abstraction

```
RepoPilot agents (backlog, coding, commit message, review)
        |
        v
AIProvider  (app/ai/base.py)              — chat(), test_connection(), list_models(), capabilities()
        |
        v
app.ai.factory.resolve_provider(user_settings, settings)   — the ONE place with provider-selection logic
        |
        v
OllamaProvider | AnthropicProvider | GeminiProvider   (app/ai/providers/*.py)
        |
        v
ollama SDK | anthropic SDK | google-genai SDK
```

- **`app/ai/types.py`** — the normalized `AIRequest` (`messages`, `system_prompt`, `tools`,
  `json_mode`, ...), `AIMessage`, `AIResponse` (`text`, `tool_calls`, `finish_reason`, `usage`),
  and a normalized error hierarchy (`AuthenticationError`, `ProviderUnavailableError`,
  `ModelUnavailableError`, `RateLimitedError`, `AITimeoutError`, `NetworkError`,
  `ConfigurationError`, `UnsupportedCapabilityError`). Every provider adapter catches its own
  SDK's exceptions and re-raises one of these — nothing upstream ever sees a raw
  `anthropic.APIStatusError` or `ollama.ResponseError`.
- **`app/ai/base.py`** — the `AIProvider` ABC.
- **`app/ai/providers/`** — one adapter per provider, each owning its own SDK usage and
  request/response translation. `OllamaProvider` also owns the recovery logic for local models
  that sometimes write a tool call as free-form JSON text instead of using the API's native
  tool-calling field (`app/ai/text_tool_calls.py`) — that's a local-model quirk, not something
  the coding agent's loop needs to know about.
- **`app/ai/factory.py`** — `resolve_provider()` is the single place that turns "this user's
  saved settings" (or the environment fallback) into a live `AIProvider` instance, and
  `validate_model_choice()` rejects an unsupported provider or an unconfirmed model before
  anything is saved or run.
- **`app/agents/coding_agent.py`** — the tool-calling loop is entirely provider-agnostic: it
  reads `AIResponse.tool_calls`/`finish_reason` and never checks which provider produced them.

## Configuring Ollama

Provider: **Ollama**. Fields: **Endpoint** (defaults to `http://localhost:11434`) and
**Model**, either typed or picked from **Refresh models** (a live `GET /api/tags` call against
the endpoint). No API key.

If RepoPilot is deployed to the cloud, the endpoint must be reachable *from the server*, not
from the browser — a `localhost` endpoint only works when Ollama runs on the same machine as
the backend (local dev). Point it at a real reachable host/IP for any other deployment.

## Configuring Anthropic

Provider: **Anthropic (Claude)**. Fields: **API Key** (write-only — never echoed back after
saving) and **Model**, restricted to a curated list confirmed compatible with RepoPilot's
tool-calling coding agent (`app/ai/providers/anthropic_provider.py::KNOWN_MODELS`).

## Configuring Gemini

Same shape as Anthropic — API key + a curated model list
(`app/ai/providers/gemini_provider.py::KNOWN_MODELS`). Gemini was already RepoPilot's second
provider before this abstraction existed; it's preserved unchanged, just moved behind the same
interface as Ollama and Anthropic.

## Adding another provider

1. Add an `AIProviderName` value in `app/models.py`.
2. Implement `AIProvider` in `app/ai/providers/<name>_provider.py`: translate `AIRequest` →
   the SDK's request shape, translate the SDK's response → `AIResponse`, and map the SDK's own
   exceptions to the normalized error hierarchy in `app/ai/types.py`.
3. Register it in `app/ai/factory.py` (`_construct`, `SUPPORTED_PROVIDERS`, and a
   `KNOWN_MODELS_BY_PROVIDER` entry if the provider needs a curated model list).
4. Add it to the frontend's provider select (`frontend/src/lib/aiProviderOptions.ts`) and the
   matching model list if curated.

No agent code changes — that's the point of the abstraction.

## Security

- API keys are encrypted at rest (`app/ai/crypto.py`, Fernet) using `AI_ENCRYPTION_KEY` (falls
  back to `SESSION_SECRET` if unset — see `.env.example`).
- Save/get endpoints (`PUT`/`GET /api/v1/ai-settings`) never return the raw key — only
  `provider`, `model`, `endpoint`, `configured`, `enabled`, `updated_at`
  (`AIConfigResponse`). Saving with `api_key` omitted keeps whichever key was already stored.
- Keys are never logged and never appear in a normalized error message.

## Scheduled runs (Autopilot)

`AutopilotScheduler` resolves the *plan owner's* AI settings on every scheduled run
(`app/autopilot_scheduler.py::_process_due`), independent of whether that user is online. A
broken configuration (bad/undecryptable key, unsupported provider) marks that one scheduled run
`skipped` or `failed` with a clear reason — it never crashes the scheduler loop or blocks other
repositories' due runs.

## Run snapshots

Every `Run` records `ai_provider`/`ai_model` (never the API key) at the point the orchestrator
resolves a provider for it, so activity history stays accurate even after a user later changes
their AI settings (`app/orchestrator.py::_execute_inner`, surfaced in the Run Detail page's info
strip).
