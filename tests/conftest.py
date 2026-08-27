"""Points the app at a throwaway SQLite file before app.main (and its module-level
Database singleton) is imported by any test module, so test runs never touch the
real local dev database and always start from a clean slate."""

from __future__ import annotations

import os
from pathlib import Path

_TEST_DB_PATH = Path(__file__).resolve().parent.parent / ".pytest-db-tmp" / "test.db"
for _suffix in ("", "-wal", "-shm"):
    _candidate = _TEST_DB_PATH.with_name(_TEST_DB_PATH.name + _suffix)
    _candidate.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(_TEST_DB_PATH)

# app.config auto-loads the project's real .env (dev convenience) but load_dotenv() never
# overrides a variable that's already set -- pinning these here, before anything imports
# app.main, keeps tests from ever picking up a real developer's GITHUB_TOKEN/allowlist/OAuth
# credentials/session secret.
os.environ.setdefault("GITHUB_TOKEN", "")
os.environ.setdefault("ALLOWED_TARGET_REPOS", "")
os.environ.setdefault("GITHUB_OAUTH_CLIENT_ID", "")
os.environ.setdefault("GITHUB_OAUTH_CLIENT_SECRET", "")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
# Tests must never depend on a real network call -- every coding/review/commit-message/
# backlog test mocks ollama.AsyncClient, which only the "ollama" provider path actually
# calls. Without pinning this, a developer's real .env (e.g. LLM_PROVIDER=gemini with a
# real, rate-limited API key) would silently make the whole suite hit the live Gemini API
# instead of the mocks -- slow, flaky, and burns real quota.
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("GEMINI_API_KEY", "")

from app.auth import SessionUser
from app.main import app, get_current_user

# Every route except /health, /api/v1/auth/*, and the webhook now requires a logged-in
# GitHub session. Overriding the dependency once, here, means no individual test file has
# to know or care about auth -- they all import the same already-overridden `app` object.
app.dependency_overrides[get_current_user] = lambda: SessionUser(
    login="test-user", name="Test User", avatar_url=None, access_token="test-access-token"
)
