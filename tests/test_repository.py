from pathlib import Path

import pytest

from app.planner import TaskPlanner
from app.repository import RepositoryAnalyzer


def test_analyzer_detects_python_todos_and_tools(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("# TODO: validate input\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok(): pass\n")

    analysis = RepositoryAnalyzer().analyze(tmp_path)

    assert analysis.languages == {"Python": 2}
    assert analysis.todo_items == ["src/app.py:1: validate input"]
    assert "pytest" in analysis.detected_tools
    assert analysis.test_directories == ["tests"]


def test_analyzer_requires_git_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="already-cloned Git"):
        RepositoryAnalyzer().analyze(tmp_path)


def test_planner_keeps_tasks_low_risk(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "main.py").write_text("# FIXME: edge condition\n")
    analysis = RepositoryAnalyzer().analyze(tmp_path)

    plan = TaskPlanner().plan(analysis)

    assert plan.tasks
    assert all(task.risk.value == "low" for task in plan.tasks)
    assert all(task.requires_human_approval for task in plan.tasks)
