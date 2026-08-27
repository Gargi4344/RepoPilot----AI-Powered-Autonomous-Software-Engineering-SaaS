from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Fills in any variable not already set in the real process environment (never overrides
# one that is) -- so a real `export`/CI-injected value always wins over the .env file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    github_webhook_secret: str | None
    github_token: str | None
    db_path: Path
    frontend_origin: str
    max_concurrent_runs: int
    test_timeout_seconds: int
    llm_provider: str
    ollama_host: str
    ollama_model: str
    gemini_api_key: str | None
    gemini_model: str
    coding_agent_max_iterations: int
    coding_agent_timeout_seconds: int
    autopilot_tick_seconds: int
    allowed_target_repos: list[str]
    github_oauth_client_id: str | None
    github_oauth_client_secret: str | None
    session_secret: str
    ai_encryption_key: str

    @classmethod
    def from_environment(cls) -> Settings:
        allowed_repos_raw = os.getenv("ALLOWED_TARGET_REPOS", "")
        return cls(
            workspace_root=Path(os.getenv("WORKSPACE_ROOT", "./data/repos")).resolve(),
            github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET") or None,
            github_token=os.getenv("GITHUB_TOKEN") or None,
            db_path=Path(os.getenv("DB_PATH", "./data/pr-engineer.db")).resolve(),
            frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
            max_concurrent_runs=int(os.getenv("MAX_CONCURRENT_RUNS", "2")),
            test_timeout_seconds=int(os.getenv("TEST_TIMEOUT_SECONDS", "300")),
            # "ollama" (default, local, zero API cost) or "gemini" (real API key, real
            # per-token cost, much more reliable native tool-calling -- no equivalent needed
            # for the malformed/embedded/repeated-tool-call recovery the Ollama path relies
            # on). One provider setting covers all four agents; there is no per-agent model
            # override for either provider, matching how OLLAMA_MODEL already worked.
            llm_provider=os.getenv("LLM_PROVIDER", "ollama").strip().lower(),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            coding_agent_max_iterations=int(os.getenv("CODING_AGENT_MAX_ITERATIONS", "25")),
            coding_agent_timeout_seconds=int(os.getenv("CODING_AGENT_TIMEOUT_SECONDS", "1800")),
            # How often the Autopilot background loop checks for due/in-flight scheduled
            # runs. Lower is more responsive to the exact configured run time; higher is
            # lighter on the database. 30s keeps a run starting within half a minute of its
            # scheduled time without polling aggressively.
            autopilot_tick_seconds=int(os.getenv("AUTOPILOT_TICK_SECONDS", "30")),
            # Empty by default -- push/PR is refused for every repo until explicitly allowlisted.
            allowed_target_repos=[repo.strip() for repo in allowed_repos_raw.split(",") if repo.strip()],
            github_oauth_client_id=os.getenv("GITHUB_OAUTH_CLIENT_ID") or None,
            github_oauth_client_secret=os.getenv("GITHUB_OAUTH_CLIENT_SECRET") or None,
            # Only a fallback for tests/environments that never touch a real session --
            # every real deployment sets this explicitly (rotating it invalidates all
            # existing sessions, so it must stay stable and secret).
            session_secret=os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me"),
            # Encrypts per-user AI provider API keys at rest (app/ai/crypto.py). Falls back to
            # session_secret so a working deployment doesn't need a brand-new secret
            # provisioned just for this -- set it explicitly in production if the two should
            # rotate independently (rotating either one invalidates data encrypted under it).
            ai_encryption_key=os.getenv("AI_ENCRYPTION_KEY") or os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me"),
        )

    @property
    def llm_model(self) -> str:
        """The model name for whichever provider is active -- lets a caller building a
        request pick the right one without repeating the llm_provider branch itself."""
        return self.gemini_model if self.llm_provider == "gemini" else self.ollama_model
