from __future__ import annotations

import json
import logging

from app.ai.base import AIProvider
from app.ai.types import AIMessage, AIRequest
from app.models import Task

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You write a single Conventional Commits message for a code change. "
    'Respond with ONLY a JSON object: {"type": "...", "scope": "...", "subject": "..."}. '
    "type is one of: feat, fix, refactor, docs, test, perf, chore. "
    "scope is a short lowercase module/area name (no spaces), or empty string if none fits. "
    "subject is an imperative, present-tense summary under 72 characters, no trailing period."
)


def _fallback(task: Task) -> str:
    return f"chore: automated changes for {task.title}"


async def generate_commit_message(task: Task, diff_text: str, *, ai_provider: AIProvider) -> str:
    """Produces a Conventional Commits message via the configured model, e.g. "fix(auth):
    validate refresh token". Falls back to a deterministic template on any failure --
    this step must never block the pipeline."""
    prompt = (
        f"Task: {task.title}\n{task.description}\n\n"
        f"Diff (truncated):\n{diff_text[:4000]}"
    )
    try:
        response = await ai_provider.chat(
            AIRequest(messages=[AIMessage(role="user", content=prompt)], system_prompt=_SYSTEM_PROMPT, json_mode=True)
        )
        data = json.loads(response.text)
        commit_type = str(data["type"]).strip()
        scope = str(data.get("scope") or "").strip()
        subject = str(data["subject"]).strip().rstrip(".")
        if not commit_type or not subject:
            raise ValueError("empty type or subject")
        header = f"{commit_type}({scope})" if scope else commit_type
        return f"{header}: {subject}"
    except Exception:
        logger.warning("Falling back to a template commit message for task %s", task.id, exc_info=True)
        return _fallback(task)
