import asyncio
import json

import httpx
import pytest

from app.github_client import (
    GitHubClientError,
    ensure_repo_allowed,
    list_user_repos,
    open_draft_pull_request,
    parse_repo_slug,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo.git", "owner/repo"),
        ("https://github.com/owner/repo", "owner/repo"),
        ("git@github.com:owner/repo.git", "owner/repo"),
        ("git@github.com:owner/repo", "owner/repo"),
        ("https://github.com/owner/repo/", "owner/repo"),
    ],
)
def test_parse_repo_slug_handles_https_and_ssh_forms(url: str, expected: str) -> None:
    assert parse_repo_slug(url) == expected


def test_parse_repo_slug_rejects_non_github_url() -> None:
    with pytest.raises(GitHubClientError, match="Could not parse"):
        parse_repo_slug("https://gitlab.com/owner/repo.git")


def test_ensure_repo_allowed_passes_for_listed_repo() -> None:
    ensure_repo_allowed("owner/repo", ["owner/repo", "other/repo"])


def test_ensure_repo_allowed_rejects_unlisted_repo() -> None:
    with pytest.raises(GitHubClientError, match="not in ALLOWED_TARGET_REPOS"):
        ensure_repo_allowed("owner/repo", [])


def test_ensure_repo_allowed_rejects_when_not_in_specific_list() -> None:
    with pytest.raises(GitHubClientError, match="not in ALLOWED_TARGET_REPOS"):
        ensure_repo_allowed("owner/repo", ["someone-else/other-repo"])


def test_list_user_repos_sends_expected_request_and_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json=[
                {
                    "name": "shiny-cards-finder",
                    "full_name": "octocat/shiny-cards-finder",
                    "description": "A demo repo",
                    "html_url": "https://github.com/octocat/shiny-cards-finder",
                    "clone_url": "https://github.com/octocat/shiny-cards-finder.git",
                    "default_branch": "main",
                    "private": False,
                    "fork": False,
                    "updated_at": "2026-08-01T00:00:00Z",
                }
            ],
        )

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.github_client.httpx.AsyncClient", fake_client)

    repos = asyncio.run(list_user_repos("gh-token"))

    assert captured["headers"]["authorization"] == "Bearer gh-token"
    assert "affiliation=owner" in captured["url"]
    assert len(repos) == 1
    assert repos[0].full_name == "octocat/shiny-cards-finder"
    assert repos[0].private is False


def test_list_user_repos_raises_on_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.github_client.httpx.AsyncClient", fake_client)

    with pytest.raises(GitHubClientError, match="401"):
        asyncio.run(list_user_repos("bad-token"))


def test_open_draft_pull_request_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"html_url": "https://github.com/owner/repo/pull/1", "number": 1})

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.github_client.httpx.AsyncClient", fake_client)

    result = asyncio.run(
        open_draft_pull_request(
            "owner/repo", "pr-engineer/fix-thing-abc123", "main", "fix: the thing", "body text", "gh-token"
        )
    )

    assert result["html_url"] == "https://github.com/owner/repo/pull/1"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.github.com/repos/owner/repo/pulls"
    assert captured["headers"]["authorization"] == "Bearer gh-token"
    assert captured["json"] == {
        "title": "fix: the thing",
        "body": "body text",
        "head": "pr-engineer/fix-thing-abc123",
        "base": "main",
        "draft": True,
    }


def test_open_draft_pull_request_raises_on_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Validation failed"})

    original_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("app.github_client.httpx.AsyncClient", fake_client)

    with pytest.raises(GitHubClientError, match="422"):
        asyncio.run(open_draft_pull_request("owner/repo", "pr-engineer/x-abc", "main", "t", "b", "tok"))
