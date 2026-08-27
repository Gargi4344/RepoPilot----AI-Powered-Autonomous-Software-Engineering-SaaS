from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import AutopilotPlanRequest, FocusArea, ScheduleType, Task, TaskStatus

PLAN_WINDOW_DAYS = 7


def compute_schedule(request: AutopilotPlanRequest, now: datetime) -> list[datetime]:
    """Expands a plan's schedule into concrete UTC datetimes over the next PLAN_WINDOW_DAYS
    days -- a bounded plan, not an unlimited recurring cron. `now` must be timezone-aware
    (UTC). A day whose run time has already passed is skipped rather than backfilled."""
    try:
        tz = ZoneInfo(request.timezone)
    except Exception:  # noqa: BLE001 -- an invalid/unknown IANA name falls back to UTC
        tz = ZoneInfo("UTC")
    hour, minute = (int(part) for part in request.run_time.split(":"))

    allowed_weekdays = _allowed_weekdays(request)
    local_now = now.astimezone(tz)
    times: list[datetime] = []
    for offset in range(PLAN_WINDOW_DAYS):
        candidate_date = (local_now + timedelta(days=offset)).date()
        if candidate_date.weekday() not in allowed_weekdays:
            continue
        candidate_local = datetime(
            candidate_date.year, candidate_date.month, candidate_date.day, hour, minute, tzinfo=tz
        )
        if candidate_local <= local_now:
            continue
        times.append(candidate_local.astimezone(ZoneInfo("UTC")))
    return times


def _allowed_weekdays(request: AutopilotPlanRequest) -> set[int]:
    if request.schedule_type == ScheduleType.daily:
        return set(range(7))
    if request.schedule_type == ScheduleType.weekdays:
        return {0, 1, 2, 3, 4}
    if request.schedule_type == ScheduleType.weekly:
        return {request.weekly_day if request.weekly_day is not None else 0}
    return set(request.custom_days) or set(range(7))  # custom with nothing picked degrades to daily


# Keyword heuristics, not a persisted task field -- classification runs at selection time so
# it works over both deterministic (repository-todo/repository-analysis) and AI-proposed
# (llm-backlog) tasks without needing a schema change to Task itself.
_KEYWORDS: dict[FocusArea, tuple[str, ...]] = {
    FocusArea.bug_fixes: ("bug", "fix", "crash", "error", "incorrect", "broken"),
    FocusArea.tests: ("test", "coverage", "pytest", "unit test", "assert"),
    FocusArea.documentation: ("doc", "readme", "comment", "docstring"),
    FocusArea.dependencies: ("dependenc", "upgrade", "bump", "package", "requirements"),
    FocusArea.security: ("security", "vulnerab", "secret", "sanitiz", "injection", "auth"),
    FocusArea.performance: ("performance", "perf", "slow", "optimi", "latency", "memory"),
    FocusArea.code_cleanup: ("cleanup", "refactor", "lint", "dead code", "unused", "duplicate"),
    FocusArea.major_features: ("implement", "new feature", "add support for", "architecture"),
}
# Checked in this order so a more specific signal (e.g. "security") wins over a generic one
# a task might also happen to mention.
_CLASSIFICATION_ORDER = (
    FocusArea.security,
    FocusArea.dependencies,
    FocusArea.tests,
    FocusArea.documentation,
    FocusArea.bug_fixes,
    FocusArea.performance,
    FocusArea.code_cleanup,
    FocusArea.major_features,
)


def classify_focus_areas(task: Task) -> set[FocusArea]:
    """Best-effort keyword classification over a task's own title/description -- not exact,
    but good enough to keep Autopilot inside the categories the user actually approved.
    Falls back to {code_cleanup} for a repository-analysis task with no stronger signal
    (those are broad hygiene checks -- e.g. "add a README" -- closer to cleanup than any
    other bucket) and {major_features} for an ungrounded AI proposal with no keyword match
    at all, so an unclassifiable task never silently matches every focus area."""
    text = f"{task.title} {task.description}".lower()
    matches = {area for area in _CLASSIFICATION_ORDER if any(kw in text for kw in _KEYWORDS[area])}
    if matches:
        return matches
    if task.source == "repository-analysis":
        return {FocusArea.code_cleanup}
    return {FocusArea.major_features}


def select_task_for_autopilot(tasks: list[Task], focus_areas: list[FocusArea]) -> Task | None:
    """Picks the single best candidate for one scheduled run: the highest-priority backlog
    task whose classification intersects the plan's allowed focus areas. `tasks` is expected
    pre-sorted by priority desc (matching Database.list_tasks_for_repository's own order),
    so the first match found here is the best one."""
    allowed = set(focus_areas)
    if not allowed:
        return None
    for task in tasks:
        if task.status != TaskStatus.backlog:
            continue
        if classify_focus_areas(task) & allowed:
            return task
    return None
