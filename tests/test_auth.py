import asyncio
import time

import httpx
import pytest

from app.auth import (
    AuthError,
    SessionUser,
    build_authorize_url,
    create_session_cookie,
    exchange_code_for_user,
    read_session_cookie,
)


def test_build_authorize_url_includes_client_id_redirect_and_state() -> None:
    url = build_authorize_url("client-123", "http://localhost:8000/api/v1/auth/github/callback", "state-abc")

    assert "client_id=client-123" in url
    assert "redirect_uri=http://localhost:8000/api/v1/auth/github/callback" in url
    assert "state=state-abc" in url
    assert "scope=public_repo" in url


def test_session_cookie_round_trips() -> None:
    user = SessionUser(
        login="octocat", name="The Octocat", avatar_url="https://example.com/a.png", access_token="gh-token"
    )

    cookie = create_session_cookie(user, "test-secret")
    recovered = read_session_cookie(cookie, "test-secret")

    assert recovered == user


def test_session_cookie_rejects_wrong_secret() -> None:
    user = SessionUser(login="octocat", name=None, avatar_url=None, access_token="gh-token")
    cookie = create_session_cookie(user, "correct-secret")

    assert read_session_cookie(cookie, "wrong-secret") is None


def test_session_cookie_rejects_garbage_value() -> None:
    assert read_session_cookie("not-a-real-cookie", "test-secret") is None


def test_session_cookie_rejects_expired_value(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SessionUser(login="octocat", name=None, avatar_url=None, access_token="gh-token")
    cookie = create_session_cookie(user, "test-secret")

    # itsdangerous compares against wall-clock time internally; jumping far enough forward
    # is the simplest way to simulate an expired session without waiting 7 real days.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 8 * 24 * 3600)

    assert read_session_cookie(cookie, "test-secret") is None


def _mock_client(handler):
    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    return fake_client


def test_exchange_code_for_user_returns_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "gh-access-token"})
        if request.url.path == "/user":
            assert request.headers["authorization"] == "Bearer gh-access-token"
            return httpx.Response(
                200, json={"login": "octocat", "name": "The Octocat", "avatar_url": "https://example.com/a.png"}
            )
        raise AssertionError(f"unexpected request: {request.url}")

    monkeypatch.setattr("app.auth.httpx.AsyncClient", _mock_client(handler))

    user = asyncio.run(
        exchange_code_for_user(
            code="abc", client_id="id", client_secret="secret", redirect_uri="http://localhost:8000/callback"
        )
    )

    assert user == SessionUser(
        login="octocat",
        name="The Octocat",
        avatar_url="https://example.com/a.png",
        access_token="gh-access-token",
    )


def test_exchange_code_for_user_raises_when_token_exchange_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error_description": "bad_verification_code"})

    monkeypatch.setattr("app.auth.httpx.AsyncClient", _mock_client(handler))

    with pytest.raises(AuthError, match="bad_verification_code"):
        asyncio.run(
            exchange_code_for_user(
                code="bad", client_id="id", client_secret="secret", redirect_uri="http://localhost:8000/callback"
            )
        )


def test_exchange_code_for_user_raises_when_profile_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "gh-access-token"})
        return httpx.Response(401, json={"message": "Bad credentials"})

    monkeypatch.setattr("app.auth.httpx.AsyncClient", _mock_client(handler))

    with pytest.raises(AuthError, match="401"):
        asyncio.run(
            exchange_code_for_user(
                code="abc", client_id="id", client_secret="secret", redirect_uri="http://localhost:8000/callback"
            )
        )
