from __future__ import annotations

import json
import logging

from app.ai.base import AIProvider
from app.ai.types import AIMessage, AIRequest
from app.models import ReviewResult, RiskLevel, Task

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You review a code diff for a small, focused change to an existing repository. "
    'Respond with ONLY a JSON object: '
    '{"approved": true/false, "summary": "...", "concerns": ["..."], "risk": "low"|"medium"|"high"}. '
    "approved is your judgement of whether this diff looks safe and correct enough to merge "
    "after a human reviews it. summary is one or two sentences. concerns is a list of specific, "
    "concrete issues -- an empty list if you found none. "
    "This review is advisory only: it is shown to a human alongside the diff and never blocks "
    "or gates anything by itself -- a human always makes the final merge decision."
)

_FALLBACK = ReviewResult(
    approved=False,
    summary="Automated review was unavailable for this change.",
    concerns=[],
    risk=RiskLevel.medium,
)


async def review_diff(task: Task, diff_text: str, *, ai_provider: AIProvider) -> ReviewResult:
    """Produces an advisory review of a diff. Never raises and never blocks the pipeline --
    on any failure it returns a clearly-labeled fallback result instead of a real review."""
    prompt = f"Task: {task.title}\n{task.description}\n\nDiff:\n{diff_text[:8000]}"
    try:
        response = await ai_provider.chat(
            AIRequest(messages=[AIMessage(role="user", content=prompt)], system_prompt=_SYSTEM_PROMPT, json_mode=True)
        )
        data = json.loads(response.text)
        return ReviewResult(
            approved=bool(data["approved"]),
            summary=str(data["summary"]).strip() or "(no summary provided)",
            concerns=[str(item) for item in (data.get("concerns") or [])],
            risk=RiskLevel(data.get("risk", "medium")),
        )
    except Exception:
        logger.warning("Review agent unavailable for task %s", task.id, exc_info=True)
        return _FALLBACK
