import base64
import subprocess
from pathlib import Path

import pytest

from app.git_ops import (
    GitOpsError,
    clone_repository,
    commit_all,
    create_worktree,
    diff_working_tree,
    pull_latest,
    push,
    resolve_default_branch,
)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_resolve_default_branch_falls_back_to_current_branch_without_remote(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    branch = resolve_default_branch(repo)

    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert branch == current


def test_resolve_default_branch_gives_an_actionable_error_for_a_repo_with_no_commits(tmp_path: Path) -> None:
    # Regression: a brand-new GitHub repo with zero commits leaves HEAD unborn. The remote
    # lookup returns "HEAD branch: (unknown)" (skipped by design) and the local fallback --
    # `git rev-parse --abbrev-ref HEAD` -- then fails with a cryptic "unknown revision"
    # message that reached the run's error_message verbatim in production. Observed against
    # a real empty repository during an Autopilot run.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    with pytest.raises(GitOpsError, match="no commits yet"):
        resolve_default_branch(repo)


def test_create_worktree_creates_isolated_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktrees_root = tmp_path / "worktrees"
    base_branch = resolve_default_branch(repo)

    worktree_path, branch_name = create_worktree(repo, worktrees_root, "run123abcd", "Fix the thing", base_branch)

    assert worktree_path.is_dir()
    assert branch_name.startswith("pr-engineer/fix-the-thing-")
    assert (worktree_path / "README.md").is_file()
    # the original checkout is untouched -- still on the base branch
    original_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert original_branch == base_branch


def test_commit_all_returns_none_when_nothing_changed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree_path, _ = create_worktree(repo, tmp_path / "worktrees", "run1", "task", resolve_default_branch(repo))

    assert commit_all(worktree_path, "chore: nothing to do") is None


def test_diff_working_tree_sees_uncommitted_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree_path, _ = create_worktree(repo, tmp_path / "worktrees", "run1", "task", resolve_default_branch(repo))

    assert diff_working_tree(worktree_path).strip() == ""

    (worktree_path / "new_file.txt").write_text("content\n")

    diff = diff_working_tree(worktree_path)
    assert "new_file.txt" in diff
    assert "content" in diff


def test_commit_all_creates_commit_when_changes_exist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree_path, _ = create_worktree(repo, tmp_path / "worktrees", "run1", "task", resolve_default_branch(repo))
    (worktree_path / "new_file.txt").write_text("content\n")

    sha = commit_all(worktree_path, "feat: add new file")

    assert sha is not None
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=worktree_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert log == "feat: add new file"


def test_clone_repository_creates_a_working_checkout(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _init_repo(source)
    dest = tmp_path / "cloned" / "demo"

    clone_repository(str(source), dest)

    assert (dest / "README.md").read_text() == "hello\n"
    assert (dest / ".git").is_dir()


def test_pull_latest_fetches_new_commits(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _init_repo(source)
    dest = tmp_path / "cloned" / "demo"
    clone_repository(str(source), dest)

    (source / "new_file.txt").write_text("new content\n")
    subprocess.run(["git", "add", "-A"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add new file"], cwd=source, check=True)

    pull_latest(dest)

    assert (dest / "new_file.txt").read_text() == "new content\n"


def test_push_refuses_branch_outside_prefix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree_path, _ = create_worktree(repo, tmp_path / "worktrees", "run1", "task", resolve_default_branch(repo))

    with pytest.raises(GitOpsError, match="Refusing to push"):
        push(worktree_path, "main")


def test_push_authenticates_with_basic_auth_not_bearer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: GitHub's REST API accepts "Authorization: Bearer <token>", but its
    # git-over-HTTPS smart protocol does not -- personal access tokens must be sent as HTTP
    # Basic auth instead. Confirmed directly against a real repo: Bearer failed even a
    # read-only `git ls-remote` with "invalid credentials"; Basic succeeded. Every push
    # was failing in production until this was fixed.
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree_path, branch_name = create_worktree(repo, tmp_path / "worktrees", "run1", "task", "main")

    captured_argv: list[str] = []

    def fake_run(argv, **kwargs):
        captured_argv.extend(argv)
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.git_ops.subprocess.run", fake_run)

    push(worktree_path, branch_name, token="my-test-token")

    header_arg = next(a for a in captured_argv if a.startswith("http.extraHeader="))
    expected_basic = base64.b64encode(b"x-access-token:my-test-token").decode()
    assert header_arg == f"http.extraHeader=Authorization: Basic {expected_basic}"


def test_push_redacts_the_auth_token_from_a_failed_push_error(tmp_path: Path) -> None:
    # Regression: a failed push's GitOpsError previously included the raw `-c
    # http.extraHeader=Authorization: Bearer <token>` argv entry verbatim -- and that
    # message gets logged, persisted to run_events, and shown in the dashboard UI. Observed
    # in production: a real GitHub token leaked into a run's activity log this way.
    repo = tmp_path / "repo"
    _init_repo(repo)
    base_branch = resolve_default_branch(repo)
    subprocess.run(["git", "remote", "add", "origin", str(tmp_path / "does-not-exist.git")], cwd=repo, check=True)
    worktree_path, branch_name = create_worktree(repo, tmp_path / "worktrees", "run1", "task", base_branch)

    secret_token = "super-secret-token-value"
    with pytest.raises(GitOpsError) as exc_info:
        push(worktree_path, branch_name, token=secret_token)

    assert secret_token not in str(exc_info.value)
    assert "***redacted***" in str(exc_info.value)


def test_push_pushes_to_local_bare_remote(tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    repo = tmp_path / "repo"
    _init_repo(repo)
    base_branch = resolve_default_branch(repo)  # resolved before adding a remote with no pushed refs yet
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    subprocess.run(["git", "push", "-q", "origin", base_branch], cwd=repo, check=True)

    worktree_path, branch_name = create_worktree(repo, tmp_path / "worktrees", "run1", "task", base_branch)
    (worktree_path / "new_file.txt").write_text("content\n")
    commit_all(worktree_path, "feat: add new file")

    push(worktree_path, branch_name)

    remote_branches = subprocess.run(
        ["git", "branch", "-r"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert f"origin/{branch_name}" in remote_branches
