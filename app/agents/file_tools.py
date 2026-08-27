from __future__ import annotations

from pathlib import Path

from app.repository import IGNORED_DIRECTORIES

DENIED_DIR_NAMES = {".git"}
DENIED_PREFIX = (".github", "workflows")


class PathGuardError(RuntimeError):
    """Raised when a tool call's path would escape the worktree or touch a denied location."""


class PathGuard:
    """Confines every file operation to a single worktree root and refuses paths that
    touch .git/**, .github/workflows/**, or .env*. Enforced here in code, not left to the
    model to avoid on its own -- this is the coding agent's security boundary against
    prompt injection from repository content and against touching CI config or secrets."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise PathGuardError(f"Path escapes the worktree: {relative_path}")
        parts = candidate.relative_to(self.root).parts
        if any(part in DENIED_DIR_NAMES or part.startswith(".env") for part in parts):
            raise PathGuardError(f"Path touches a denied location: {relative_path}")
        if parts[: len(DENIED_PREFIX)] == DENIED_PREFIX:
            raise PathGuardError(f"Path touches a denied location: {relative_path}")
        return candidate


class FileTools:
    """Filesystem operations available to the coding agent, all routed through a PathGuard."""

    def __init__(self, guard: PathGuard) -> None:
        self._guard = guard

    def read_file(self, path: str) -> str:
        target = self._guard.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> str:
        target = self._guard.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {path}"

    def str_replace(self, path: str, old_str: str, new_str: str) -> str:
        target = self._guard.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_str)
        if count == 0:
            raise ValueError("old_str was not found in the file")
        if count > 1:
            raise ValueError(f"old_str is not unique in the file ({count} occurrences)")
        target.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Replaced 1 occurrence in {path}"

    def list_files(self, path: str = ".") -> str:
        target = self._guard.resolve(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries: list[str] = []
        for candidate in sorted(target.rglob("*")):
            relative = candidate.relative_to(self._guard.root)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                continue
            entries.append(relative.as_posix() + ("/" if candidate.is_dir() else ""))
            if len(entries) >= 300:
                entries.append("... (truncated)")
                break
        return "\n".join(entries) or "(empty)"
