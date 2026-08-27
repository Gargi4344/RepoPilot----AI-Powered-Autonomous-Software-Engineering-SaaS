from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path

BRANCH_PREFIX = "pr-engineer/"


class GitOpsError(RuntimeError):
    """Raised when a git operation fails, or would violate a safety invariant
    (such as pushing a branch outside the pr-engineer/* namespace)."""


def _redact(argv: list[str]) -> list[str]:
    # push() passes the GitHub token as a literal `-c http.extraHeader=Authorization: Bearer
    # <token>` argv entry -- if a command fails, that entry must never end up in a raised
    # GitOpsError, since those messages get logged, persisted to run_events, and shown in
    # the UI (a real leak observed in production: the token appeared verbatim in the
    # dashboard's run log after a failed push).
    return ["***redacted***" if arg.startswith("http.extraHeader=Authorization:") else arg for arg in argv]


def _run(argv: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=False, check=False)
    if result.returncode != 0:
        raise GitOpsError(f"git command failed ({' '.join(_redact(argv))}): {result.stderr.strip()}")
    return result


def resolve_default_branch(repo_path: Path) -> str:
    """Best-effort default branch resolution: prefer the remote's HEAD branch, falling
    back to the current checked-out branch for repositories with no remote configured
    (e.g. local test/demo repos)."""
    try:
        result = _run(["git", "remote", "show", "origin"], cwd=repo_path)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("HEAD branch:"):
                branch = line.split(":", 1)[1].strip()
                if branch and branch != "(unknown)":
                    return branch
    except GitOpsError:
        pass
    try:
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    except GitOpsError as exc:
        # An unborn HEAD (e.g. a brand-new GitHub repo with no initial commit) fails this
        # command with a cryptic "unknown revision" message -- there's no commit anywhere to
        # base a worktree branch off, so surface why in terms a user can act on instead.
        if "unknown revision" in str(exc) or "ambiguous argument" in str(exc):
            raise GitOpsError(
                "This repository has no commits yet. Add an initial commit (for example a README) "
                "on the default branch before running PR Engineer against it."
            ) from exc
        raise
    return result.stdout.strip()


def get_remote_url(repo_path: Path) -> str | None:
    """Returns the origin remote URL, or None if there is no origin (e.g. a local-only
    test/demo repo) -- used to resolve which GitHub repo a push/PR would target."""
    try:
        result = _run(["git", "remote", "get-url", "origin"], cwd=repo_path)
        return result.stdout.strip() or None
    except GitOpsError:
        return None


def clone_repository(clone_url: str, dest: Path, *, timeout: int = 180) -> None:
    """Clones a repo the user picked from their GitHub repo list. No authentication is
    needed -- this app's OAuth scope is public_repo only, so every repo reachable through
    the picker is public and clonable anonymously; the user's token is only ever needed
    later, for pushing a branch back."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", clone_url, str(dest)], cwd=dest.parent, timeout=timeout)


def pull_latest(repo_path: Path) -> None:
    """Fast-forward only -- refuses to silently discard local state if the checkout has
    unexpected local commits (it shouldn't, since this app never commits to it directly,
    only to worktrees, but a fast-forward-only pull is the safe default regardless)."""
    _run(["git", "pull", "--ff-only"], cwd=repo_path, timeout=120)


def slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].strip("-") or "task"


def create_worktree(
    repo_path: Path, worktrees_root: Path, run_id: str, task_title: str, base_branch: str
) -> tuple[Path, str]:
    """Creates a new isolated worktree, checked out on a freshly created pr-engineer/* branch
    based off base_branch. The original checkout at repo_path is never touched."""
    branch_name = f"{BRANCH_PREFIX}{slugify(task_title)}-{run_id[:8]}"
    worktree_path = worktrees_root / run_id
    worktrees_root.mkdir(parents=True, exist_ok=True)
    _run(["git", "worktree", "add", str(worktree_path), "-b", branch_name, base_branch], cwd=repo_path)
    return worktree_path, branch_name


def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    _run(["git", "worktree", "remove", str(worktree_path), "--force"], cwd=repo_path)


def commit_all(
    worktree_path: Path, message: str, author_name: str = "PR Engineer", author_email: str = "pr-engineer@localhost"
) -> str | None:
    """Stages and commits all changes in the worktree under a fixed bot identity.
    Returns the new commit SHA, or None if there was nothing to commit."""
    _run(["git", "add", "-A"], cwd=worktree_path)
    status = _run(["git", "status", "--porcelain"], cwd=worktree_path)
    if not status.stdout.strip():
        return None
    _run(
        ["git", "-c", f"user.name={author_name}", "-c", f"user.email={author_email}", "commit", "-m", message],
        cwd=worktree_path,
    )
    sha = _run(["git", "rev-parse", "HEAD"], cwd=worktree_path)
    return sha.stdout.strip()


def diff_against_base(worktree_path: Path, base_branch: str) -> str:
    """Diff between the base branch and HEAD -- i.e. already-committed changes. Used after
    a commit exists (PR body, review agent), not to detect uncommitted work in progress."""
    result = _run(["git", "diff", f"{base_branch}...HEAD"], cwd=worktree_path)
    return result.stdout


def diff_working_tree(worktree_path: Path) -> str:
    """Stages all changes and returns the staged diff. Unlike diff_against_base, this sees
    uncommitted changes -- use it to decide whether the coding agent produced anything to
    commit, and to summarize that diff for the commit message, before commit_all runs."""
    _run(["git", "add", "-A"], cwd=worktree_path)
    result = _run(["git", "diff", "--cached"], cwd=worktree_path)
    return result.stdout


def push(worktree_path: Path, branch_name: str, token: str | None = None) -> None:
    """Pushes only a pr-engineer/* branch, never the base branch. The namespace check is
    enforced here in code, not left to caller convention, so a bug upstream can't push
    directly to a protected branch."""
    if not branch_name.startswith(BRANCH_PREFIX):
        raise GitOpsError(f"Refusing to push a branch outside the {BRANCH_PREFIX} namespace: {branch_name}")
    argv = ["git"]
    if token:
        # GitHub's REST API accepts "Authorization: Bearer <token>", but its git-over-HTTPS
        # smart protocol does not -- personal access tokens (classic or fine-grained) must be
        # sent as HTTP Basic auth instead (username is arbitrary; GitHub only checks the
        # password/token). Confirmed directly: Bearer fails even a read-only `git ls-remote`
        # with "invalid credentials", Basic succeeds.
        basic_auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        argv += ["-c", f"http.extraHeader=Authorization: Basic {basic_auth}"]
    argv += ["push", "-u", "origin", branch_name]
    _run(argv, cwd=worktree_path, timeout=120)
