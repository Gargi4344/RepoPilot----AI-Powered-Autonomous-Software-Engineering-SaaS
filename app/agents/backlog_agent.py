from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path

from app.agents.file_tools import FileTools, PathGuard, PathGuardError
from app.ai.base import AIProvider
from app.ai.types import AIMessage, AIRequest
from app.models import ProjectAnalysis, RiskLevel, Task, TaskStatus

logger = logging.getLogger(__name__)

MAX_GENERATED_TASKS = 6

_SYSTEM_PROMPT = (
    "You are a senior software engineer doing a first-pass review of an unfamiliar codebase, "
    "looking for a handful of concrete, well-scoped, low-to-medium-risk improvements someone "
    "could safely make -- bug fixes, missing test coverage for a specific module, small "
    "refactors, documentation gaps, dependency or config issues, accessibility, or performance. "
    "Do not propose large rewrites, architecture changes, or anything that touches secrets, "
    "CI/CD config, or dependency major-version bumps. "
    'Respond with ONLY a JSON object: {"tasks": [{"title": "...", "description": "...", '
    '"priority": 1-5, "risk": "low"|"medium"|"high", "affected_files": ["..."]}]}. '
    f"Propose at most {MAX_GENERATED_TASKS} tasks. Each title is a short imperative summary; "
    "each description explains what to do and why, in 1-3 sentences. Every task will require "
    "a human's explicit approval before any code is written -- you are only proposing "
    "candidates, not deciding what happens."
)


async def generate_tasks(repository_path: Path, analysis: ProjectAnalysis, *, ai_provider: AIProvider) -> list[Task]:
    """Reads a broad, read-only snapshot of the repo (file tree, README, primary manifest)
    and asks the configured model to propose a handful of candidate tasks -- richer than the
    deterministic planner's fixed three checks. Never raises: on any failure it logs a
    warning and returns an empty list, the same fallback behavior as the other agents."""
    try:
        tools = FileTools(PathGuard(repository_path))
        file_listing = tools.list_files(".")
        readme = _read_first_existing(tools, ["README.md", "readme.md"])
        manifest = _read_first_existing(tools, analysis.manifests)

        prompt = (
            f"Project summary: {analysis.summary}\n"
            f"Languages: {analysis.languages}\n"
            f"Detected tooling: {', '.join(analysis.detected_tools) or 'none'}\n"
            f"Existing TODOs already tracked separately: {len(analysis.todo_items)}\n\n"
            f"File listing:\n{file_listing[:4000]}\n\n"
            f"README (truncated):\n{(readme or '(none)')[:2000]}\n\n"
            f"Primary manifest (truncated):\n{(manifest or '(none)')[:2000]}"
        )

        response = await ai_provider.chat(
            AIRequest(messages=[AIMessage(role="user", content=prompt)], system_prompt=_SYSTEM_PROMPT, json_mode=True)
        )
        data = json.loads(response.text)
        proposals = data.get("tasks", [])
        if not isinstance(proposals, list):
            return []

        required_checks = [tool for tool in analysis.detected_tools if tool != "GitHub Actions"]
        tasks = [_to_task(analysis.root, proposal, required_checks) for proposal in proposals[:MAX_GENERATED_TASKS]]
        return [task for task in tasks if task is not None]
    except Exception:
        logger.warning("Backlog agent unavailable for %s", repository_path, exc_info=True)
        return []


def _read_first_existing(tools: FileTools, candidates: list[str]) -> str | None:
    for path in candidates:
        try:
            return tools.read_file(path)
        except (FileNotFoundError, PathGuardError):
            continue
    return None


def _to_task(repo_root: str, proposal: object, required_checks: list[str]) -> Task | None:
    if not isinstance(proposal, dict):
        return None
    title = str(proposal.get("title") or "").strip()
    description = str(proposal.get("description") or "").strip()
    if not title or not description:
        return None
    try:
        priority = max(1, min(5, int(proposal.get("priority", 3))))
    except (TypeError, ValueError):
        priority = 3
    try:
        risk = RiskLevel(proposal.get("risk", "low"))
    except ValueError:
        risk = RiskLevel.low
    affected_files = proposal.get("affected_files")
    if not isinstance(affected_files, list):
        affected_files = []

    fingerprint = f"{repo_root}:llm:{title}:{description}"
    return Task(
        id=sha256(fingerprint.encode()).hexdigest()[:12],
        title=title,
        description=description,
        priority=priority,
        risk=risk,
        affected_files=[str(item) for item in affected_files],
        required_checks=required_checks or ["project CI"],
        source="llm-backlog",
        requires_human_approval=True,
        status=TaskStatus.backlog,
    )
