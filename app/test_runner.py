from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.models import TestOutcome

# Fixed, literal argv per tool -- never a string built from task/model output, so nothing
# the coding agent or a task's content says can influence what actually gets executed.
TOOL_COMMANDS: dict[str, list[str]] = {
    "pytest": [sys.executable, "-m", "pytest"],
    "ruff": [sys.executable, "-m", "ruff", "check", "."],
    "npm": ["npm", "test", "--silent"],
    "eslint": ["npx", "--yes", "eslint", "."],
    "go test": ["go", "test", "./..."],
}

# Tools that need node_modules to be present before they can run meaningfully.
_NODE_TOOLS = {"npm", "eslint"}


class AllowlistedTestRunner:
    """Executes only the fixed commands above, and only for tools the analyzer already
    detected in the target repository. Output is truncated before being persisted/streamed
    so a noisy test run can't blow up the run log."""

    def __init__(self, timeout_seconds: int = 300) -> None:
        self._timeout_seconds = timeout_seconds

    def run(self, worktree_path: Path, detected_tools: list[str]) -> list[TestOutcome]:
        outcomes: list[TestOutcome] = []
        # Worktrees never carry over node_modules (it's gitignored), so any freshly-created
        # worktree for a JS/TS repo would otherwise fail every npm/eslint check with a
        # confusing "package not found" error that has nothing to do with the task at hand.
        if self._needs_npm_install(worktree_path, detected_tools):
            outcomes.append(self._run_one(worktree_path, "npm install", ["npm", "install"]))
        outcomes.extend(
            self._run_one(worktree_path, tool, argv)
            for tool in detected_tools
            if (argv := TOOL_COMMANDS.get(tool)) is not None
        )
        return outcomes

    @staticmethod
    def _needs_npm_install(worktree_path: Path, detected_tools: list[str]) -> bool:
        return (
            any(tool in _NODE_TOOLS for tool in detected_tools)
            and (worktree_path / "package.json").is_file()
            and not (worktree_path / "node_modules").is_dir()
        )

    def _run_one(self, worktree_path: Path, tool: str, argv: list[str]) -> TestOutcome:
        started = time.monotonic()
        # Resolve argv[0] through PATH/PATHEXT ourselves (shutil.which, not shell=True) --
        # on Windows, subprocess.run cannot spawn "npm"/"npx" directly (they're .cmd shims;
        # CreateProcess doesn't do PATHEXT resolution the way a real shell does), which
        # otherwise raises an unhandled FileNotFoundError and crashes the whole run instead
        # of just this one check.
        resolved = shutil.which(argv[0])
        if resolved is None:
            return TestOutcome(
                tool=tool,
                exit_code=127,
                stdout="",
                stderr=f"Command not found: {argv[0]} (is it installed and on PATH?)",
                duration_seconds=round(time.monotonic() - started, 2),
            )
        try:
            result = subprocess.run(
                [resolved, *argv[1:]],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                shell=False,
                check=False,
            )
            exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = f"Timed out after {self._timeout_seconds}s"
        except OSError as exc:
            # Belt-and-suspenders: shutil.which found a candidate but spawning it still
            # failed (permissions, a broken shim, etc.) -- report it, don't crash the run.
            exit_code = 127
            stdout = ""
            stderr = f"Failed to run {argv[0]}: {exc}"
        return TestOutcome(
            tool=tool,
            exit_code=exit_code,
            stdout=stdout[-8000:],
            stderr=stderr[-4000:],
            duration_seconds=round(time.monotonic() - started, 2),
        )
