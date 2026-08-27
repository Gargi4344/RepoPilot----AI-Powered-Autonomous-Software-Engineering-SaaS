import dataclasses

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth import STATE_COOKIE
from app.main import app, get_current_user


def test_protected_route_requires_a_session(tmp_path) -> None:
    # conftest.py overrides get_current_user for every other test so they don't have to
    # know about auth -- this test proves the gate is actually real underneath that
    # override, not just trusted to exist.
    saved = app.dependency_overrides.pop(get_current_user)
    try:
        response = TestClient(app).get("/api/v1/repositories")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = saved


def test_health_and_auth_endpoints_stay_public_without_a_session() -> None:
    saved = app.dependency_overrides.pop(get_current_user)
    try:
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        # No GITHUB_OAUTH_CLIENT_ID configured in the test environment (conftest.py pins
        # it empty) -- 503 "not configured" still proves this route itself isn't
        # auth-gated, since a gated route would 401 before ever reaching that check.
        assert client.get("/api/v1/auth/github/login", follow_redirects=False).status_code == 503
    finally:
        app.dependency_overrides[get_current_user] = saved


def test_full_login_and_callback_flow_sets_a_working_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        dataclasses.replace(
            main_module.settings,
            github_oauth_client_id="test-client-id",
            github_oauth_client_secret="test-client-secret",
        ),
    )
    saved = app.dependency_overrides.pop(get_current_user)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "gh-access-token"})
        return httpx.Response(200, json={"login": "octocat", "name": "The Octocat", "avatar_url": None})

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.auth.httpx.AsyncClient", fake_client)

    try:
        client = TestClient(app)

        login_response = client.get("/api/v1/auth/github/login", follow_redirects=False)
        assert login_response.status_code in (302, 307)
        assert "github.com/login/oauth/authorize" in login_response.headers["location"]
        state_cookie = login_response.cookies[STATE_COOKIE]

        callback_response = client.get(
            "/api/v1/auth/github/callback",
            params={"code": "test-code", "state": state_cookie},
            follow_redirects=False,
        )
        assert callback_response.status_code in (302, 307)
        assert callback_response.headers["location"].endswith("/repositories")

        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 200
        assert me_response.json() == {"login": "octocat", "name": "The Octocat", "avatar_url": None}

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 204
        client.cookies.clear()
        assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = saved


def test_callback_rejects_mismatched_state() -> None:
    saved = app.dependency_overrides.pop(get_current_user)
    try:
        client = TestClient(app)
        client.cookies.set(STATE_COOKIE, "the-real-state")

        response = client.get(
            "/api/v1/auth/github/callback",
            params={"code": "test-code", "state": "an-attacker-supplied-state"},
        )

        assert response.status_code == 400
    finally:
        app.dependency_overrides[get_current_user] = saved
