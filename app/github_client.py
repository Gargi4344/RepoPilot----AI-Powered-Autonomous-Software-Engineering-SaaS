from __future__ import annotations

import re

import httpx

from app.models import GitHubRepo

GITHUB_API_BASE = "https://api.github.com"
_REMOTE_URL_PATTERN = re.compile(r"github\.com[:/]+([^/]+)/(.+?)(?:\.git)?/?$")


class GitHubClientError(RuntimeError):
    """Raised when a GitHub API call fails, or a push/PR is attempted against a repo
    that isn't on the configured allowlist."""


def parse_repo_slug(remote_url: str) -> str:
    """Extracts "owner/repo" from a GitHub remote URL, https or ssh form."""
    match = _REMOTE_URL_PATTERN.search(remote_url.strip())
    if not match:
        raise GitHubClientError(f"Could not parse a GitHub owner/repo from remote URL: {remote_url}")
    return f"{match.group(1)}/{match.group(2)}"


def ensure_repo_allowed(repo_slug: str, allowed_repos: list[str]) -> None:
    """Enforced independently of whatever path was analyzed -- defense in depth alongside
    git_ops.push()'s branch-name assertion, so a bug elsewhere can't push/PR to a repo the
    operator never explicitly allowlisted."""
    if repo_slug not in allowed_repos:
        raise GitHubClientError(f"Refusing to push/open a PR against {repo_slug}: not in ALLOWED_TARGET_REPOS")


async def list_user_repos(token: str) -> list[GitHubRepo]:
    """Lists the logged-in user's own repositories (affiliation=owner) -- the OAuth scope
    is public_repo only, so GitHub naturally excludes private repos from this response;
    there's nothing further to filter here."""
    async with httpx.AsyncClient(base_url=GITHUB_API_BASE, timeout=30) as client:
        response = await client.get(
            "/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"affiliation": "owner", "sort": "updated", "per_page": 100},
        )
    if response.status_code >= 400:
        raise GitHubClientError(f"GitHub API error {response.status_code}: {response.text[:500]}")
    return [
        GitHubRepo(
            name=repo["name"],
            full_name=repo["full_name"],
            description=repo.get("description"),
            html_url=repo["html_url"],
            clone_url=repo["clone_url"],
            default_branch=repo["default_branch"],
            private=repo["private"],
            fork=repo["fork"],
            updated_at=repo["updated_at"],
        )
        for repo in response.json()
    ]


async def open_draft_pull_request(
    repo_slug: str, branch_name: str, base_branch: str, title: str, body: str, token: str
) -> dict:
    """Always opens the PR as a draft -- there is no code path anywhere in this app that
    merges a PR; that stays a human, on GitHub, by design."""
    owner, repo = repo_slug.split("/", 1)
    async with httpx.AsyncClient(base_url=GITHUB_API_BASE, timeout=30) as client:
        response = await client.post(
            f"/repos/{owner}/{repo}/pulls",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "body": body, "head": branch_name, "base": base_branch, "draft": True},
        )
    if response.status_code >= 400:
        raise GitHubClientError(f"GitHub API error {response.status_code}: {response.text[:500]}")
    return response.json()
