from pathlib import Path

import pytest

from app.agents.file_tools import FileTools, PathGuard, PathGuardError


def _tools(root: Path) -> FileTools:
    return FileTools(PathGuard(root))


def test_read_write_round_trip(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    tools.write_file("src/app.py", "print('hi')\n")

    assert tools.read_file("src/app.py") == "print('hi')\n"


def test_str_replace_requires_unique_match(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    tools.write_file("a.py", "x = 1\nx = 1\n")

    with pytest.raises(ValueError, match="not unique"):
        tools.str_replace("a.py", "x = 1", "x = 2")


def test_str_replace_applies_single_match(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    tools.write_file("a.py", "def add(a, b):\n    return a + b\n")

    tools.str_replace("a.py", "return a + b", "return a + b  # validated")

    assert "validated" in tools.read_file("a.py")


def test_read_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _tools(tmp_path).read_file("does_not_exist.py")


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "../../etc/passwd",
        "sub/../../outside.txt",
    ],
)
def test_path_traversal_outside_root_is_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(PathGuardError, match="escapes the worktree"):
        _tools(tmp_path).write_file(path, "malicious")


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        "sub/.git/HEAD",
        ".env",
        ".env.local",
        "config/.env.production",
        ".github/workflows/deploy.yml",
    ],
)
def test_denied_locations_are_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(PathGuardError, match="denied location"):
        _tools(tmp_path).write_file(path, "malicious")


def test_absolute_path_escaping_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(PathGuardError, match="escapes the worktree"):
        _tools(tmp_path).write_file(str(outside), "malicious")


def test_list_files_excludes_ignored_directories(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    tools.write_file("src/app.py", "print(1)\n")
    tools.write_file(".venv/lib/site-packages/pkg.py", "junk\n")
    tools.write_file("node_modules/dep/index.js", "junk\n")

    listing = tools.list_files(".")

    assert "src/app.py" in listing
    assert ".venv" not in listing
    assert "node_modules" not in listing
