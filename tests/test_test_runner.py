import json
import shutil
from pathlib import Path

import pytest

from app.test_runner import TOOL_COMMANDS, AllowlistedTestRunner


def test_runner_ignores_tools_without_a_mapped_command(tmp_path: Path) -> None:
    outcomes = AllowlistedTestRunner().run(tmp_path, ["GitHub Actions", "some-unknown-tool"])

    assert outcomes == []


def test_runner_runs_pytest_and_reports_success(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")

    outcomes = AllowlistedTestRunner().run(tmp_path, ["pytest"])

    assert len(outcomes) == 1
    assert outcomes[0].tool == "pytest"
    assert outcomes[0].exit_code == 0


def test_runner_runs_pytest_and_reports_failure(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text("def test_fails():\n    assert False\n")

    outcomes = AllowlistedTestRunner().run(tmp_path, ["pytest"])

    assert outcomes[0].exit_code != 0
    assert "test_fails" in outcomes[0].stdout


def test_runner_never_executes_a_model_supplied_command(tmp_path: Path) -> None:
    # The tool name is looked up in a fixed dict -- an unrecognized "tool" (however it
    # was produced) can never cause a command to run at all.
    outcomes = AllowlistedTestRunner().run(tmp_path, ["rm -rf /"])

    assert outcomes == []


def test_runner_reports_missing_executable_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: on Windows, subprocess.run can't spawn "npm"/"npx" directly (they're
    # .cmd shims) and raises an unhandled FileNotFoundError -- which used to crash the
    # entire run instead of just failing this one check. Any genuinely-missing executable
    # (not installed, typo'd, whatever) must degrade to a reported outcome, not a crash.
    monkeypatch.setitem(TOOL_COMMANDS, "npm", ["definitely-not-a-real-executable-xyz", "test"])

    outcomes = AllowlistedTestRunner().run(tmp_path, ["npm"])

    assert len(outcomes) == 1
    assert outcomes[0].tool == "npm"
    assert outcomes[0].exit_code == 127
    assert "not found" in outcomes[0].stderr.lower()


def test_runner_resolves_and_runs_npm_on_this_platform(tmp_path: Path) -> None:
    # The actual bug scenario: a JS/TS repo's detected "npm" tool must run successfully
    # (via shutil.which's PATHEXT-aware resolution), not just fail gracefully.
    if shutil.which("npm") is None:
        pytest.skip("npm is not installed in this environment")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "scripts": {"test": "node -e \"process.exit(0)\""}})
    )
    (tmp_path / "node_modules").mkdir()  # already installed -- no install step expected

    outcomes = AllowlistedTestRunner().run(tmp_path, ["npm"])

    assert len(outcomes) == 1
    assert outcomes[0].tool == "npm"
    assert outcomes[0].exit_code == 0


def test_runner_installs_node_modules_before_running_npm_when_missing(tmp_path: Path) -> None:
    # Regression: worktrees never carry over node_modules (it's gitignored), so a freshly
    # created worktree for a JS/TS repo would otherwise fail every npm/eslint check with a
    # "package not found" error unrelated to the task -- confirmed against a real repo where
    # this made every single run unwinnable regardless of what the coding agent did.
    if shutil.which("npm") is None:
        pytest.skip("npm is not installed in this environment")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": {}, "scripts": {"test": "node -e \"process.exit(0)\""}})
    )

    outcomes = AllowlistedTestRunner().run(tmp_path, ["npm"])

    # npm may skip creating node_modules entirely when there are zero dependencies to
    # install -- what matters is that "npm install" ran (and succeeded) before "npm" did.
    assert [o.tool for o in outcomes] == ["npm install", "npm"]
    assert outcomes[0].exit_code == 0
    assert outcomes[1].exit_code == 0


def test_runner_skips_npm_install_for_non_node_tools(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")

    outcomes = AllowlistedTestRunner().run(tmp_path, ["pytest"])

    assert [o.tool for o in outcomes] == ["pytest"]
