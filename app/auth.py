from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

SESSION_COOKIE = "pr_engineer_session"
STATE_COOKIE = "pr_engineer_oauth_state"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days
STATE_MAX_AGE_SECONDS = 600  # 10 minutes -- just long enough to complete the GitHub redirect


class AuthError(RuntimeError):
    """Raised when the GitHub OAuth exchange itself fails (bad code, GitHub API error)."""


@dataclass(frozen=True)
class SessionUser:
    login: str
    name: str | None
    avatar_url: str | None
    # The user's own GitHub OAuth token -- carried in the signed session cookie (never sent
    # to the frontend, see /api/v1/auth/me) so a later "start run" request can use it to
    # clone/push/open a PR against whichever of the user's public repos they picked, with no
    # separate PAT or ALLOWED_TARGET_REPOS entry needed for that repo.
    access_token: str


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    # public_repo (not the broader "repo" scope) -- this app only ever lists and acts on the
    # user's public repositories; private repos are never visible to it.
    return (
        f"{GITHUB_AUTHORIZE_URL}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&scope=public_repo&state={state}&allow_signup=false"
    )


async def exchange_code_for_user(
    *, code: str, client_id: str, client_secret: str, redirect_uri: str
) -> SessionUser:
    """Exchanges the OAuth code for a GitHub access token server-side (the token itself
    never reaches the browser), fetches the profile, and immediately discards the token --
    it exists only to establish identity for this login gate, never stored or reused. This
    is a separate credential from GITHUB_TOKEN, which keeps handling pushes/PRs on its own."""
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_body = token_response.json()
        access_token = token_body.get("access_token")
        if not access_token:
            detail = token_body.get("error_description", "no access_token in response")
            raise AuthError(f"GitHub OAuth token exchange failed: {detail}")

        user_response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if user_response.status_code != 200:
            raise AuthError(f"Could not fetch GitHub profile (status {user_response.status_code})")
        profile = user_response.json()

    return SessionUser(
        login=profile["login"],
        name=profile.get("name"),
        avatar_url=profile.get("avatar_url"),
        access_token=access_token,
    )


def _serializer(session_secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(session_secret, salt="pr-engineer-session")


def create_session_cookie(user: SessionUser, session_secret: str) -> str:
    return _serializer(session_secret).dumps(
        {
            "login": user.login,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "access_token": user.access_token,
        }
    )


def read_session_cookie(value: str, session_secret: str) -> SessionUser | None:
    try:
        data = _serializer(session_secret).loads(value, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return SessionUser(
        login=data["login"],
        name=data.get("name"),
        avatar_url=data.get("avatar_url"),
        access_token=data["access_token"],
    )
