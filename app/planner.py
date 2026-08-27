from __future__ import annotations

from hashlib import sha256

from app.models import ProjectAnalysis, RiskLevel, Task, TaskPlan


class TaskPlanner:
    """Creates only reviewable, low-risk candidate tasks in the MVP."""

    def plan(self, analysis: ProjectAnalysis) -> TaskPlan:
        tasks: list[Task] = []
        for todo in analysis.todo_items[:10]:
            path = todo.split(":", 1)[0]
            tasks.append(self._task(
                analysis, title=f"Resolve tracked follow-up in {path}", description=todo, priority=3,
                affected_files=[path], required_checks=self._checks(analysis), source="repository-todo",
            ))
        if not analysis.test_directories and analysis.source_files:
            tasks.append(self._task(
                analysis, title="Establish a focused test baseline",
                description="Add a small test suite around the most critical existing behavior before broader changes.",
                priority=4, affected_files=[], required_checks=self._checks(analysis), source="repository-analysis",
            ))
        if not analysis.readme_present and analysis.source_files:
            tasks.append(self._task(
                analysis, title="Document local development and validation",
                description="Create or improve README instructions for setup, tests, linting, and expected contribution workflow.",
                priority=2, affected_files=["README.md"], required_checks=self._checks(analysis), source="repository-analysis",
            ))
        return TaskPlan(analysis=analysis, tasks=tasks[:10])

    @staticmethod
    def _checks(analysis: ProjectAnalysis) -> list[str]:
        return [tool for tool in analysis.detected_tools if tool != "GitHub Actions"] or ["project CI"]

    @staticmethod
    def _task(analysis: ProjectAnalysis, **values: object) -> Task:
        # Scoped to analysis.root so two different repositories that happen to produce the
        # same generic task text (e.g. both missing a README) never collide on task id --
        # task id is a persisted, globally-looked-up primary key, not just a per-response label.
        fingerprint = f"{analysis.root}:{values['title']}:{values['description']}"
        return Task(id=sha256(fingerprint.encode()).hexdigest()[:12], risk=RiskLevel.low, **values)
