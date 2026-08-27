from datetime import UTC, datetime, timedelta

import pytest

from app.autopilot import (
    PLAN_WINDOW_DAYS,
    classify_focus_areas,
    compute_schedule,
    select_task_for_autopilot,
)
from app.models import AutopilotPlanRequest, FocusArea, RiskLevel, ScheduleType, Task, TaskStatus


def _request(**overrides) -> AutopilotPlanRequest:
    defaults = {"schedule_type": ScheduleType.daily, "run_time": "09:00", "timezone": "UTC"}
    defaults.update(overrides)
    return AutopilotPlanRequest(**defaults)


def _task(task_id: str, title: str, description: str = "", source: str = "repository-todo") -> Task:
    return Task(id=task_id, title=title, description=description, priority=3, risk=RiskLevel.low, source=source)


# -- compute_schedule ---------------------------------------------------------------------


def test_daily_schedule_produces_one_run_per_day_for_the_full_window() -> None:
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)  # Monday, well before 09:00
    request = _request(schedule_type=ScheduleType.daily)

    schedule = compute_schedule(request, now)

    assert len(schedule) == PLAN_WINDOW_DAYS
    assert all(dt.hour == 9 and dt.minute == 0 for dt in schedule)
    assert schedule == sorted(schedule)


def test_weekdays_schedule_skips_saturday_and_sunday() -> None:
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)  # Monday
    request = _request(schedule_type=ScheduleType.weekdays)

    schedule = compute_schedule(request, now)

    assert all(dt.weekday() < 5 for dt in schedule)
    # The 7-day window starting Monday covers Mon..Sun -- only that week's 5 weekdays fall
    # inside it; the following Monday is one day past the window's edge.
    assert len(schedule) == 5


def test_weekly_schedule_produces_a_single_run_on_the_chosen_day() -> None:
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)  # Monday
    request = _request(schedule_type=ScheduleType.weekly, weekly_day=2)  # Wednesday

    schedule = compute_schedule(request, now)

    assert len(schedule) == 1
    assert schedule[0].astimezone(UTC).weekday() == 2


def test_custom_schedule_only_fires_on_the_selected_days() -> None:
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)  # Monday
    request = _request(schedule_type=ScheduleType.custom, custom_days=[1, 3])  # Tue, Thu

    schedule = compute_schedule(request, now)

    assert {dt.astimezone(UTC).weekday() for dt in schedule} == {1, 3}
    assert len(schedule) == 2  # one Tue + one Thu within the 7-day window


def test_a_run_time_already_passed_today_is_not_backfilled_for_today() -> None:
    now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)  # Monday, after 09:00
    request = _request(schedule_type=ScheduleType.daily, run_time="09:00")

    schedule = compute_schedule(request, now)

    assert all(dt.date() > now.date() for dt in schedule)
    assert len(schedule) == PLAN_WINDOW_DAYS - 1


def test_schedule_is_computed_in_the_configured_timezone_then_converted_to_utc() -> None:
    # 09:00 in America/New_York is 14:00 UTC during winter (EST, UTC-5).
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    request = _request(schedule_type=ScheduleType.daily, run_time="09:00", timezone="America/New_York")

    schedule = compute_schedule(request, now)

    # ZoneInfo("UTC") and datetime.UTC are different tzinfo objects for the same offset --
    # compare the actual offset, not object identity.
    assert all(dt.utcoffset() == timedelta(0) for dt in schedule)
    assert schedule[0].hour == 14


def test_an_unknown_timezone_falls_back_to_utc_instead_of_raising() -> None:
    now = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    request = _request(schedule_type=ScheduleType.daily, run_time="09:00", timezone="Not/A_Real_Zone")

    schedule = compute_schedule(request, now)

    assert schedule[0].hour == 9


# -- classify_focus_areas -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Fix crash on empty input", "The parser throws an unhandled error", FocusArea.bug_fixes),
        ("Add unit test coverage for parser", "", FocusArea.tests),
        ("Update README with setup instructions", "", FocusArea.documentation),
        ("Bump requests dependency", "Upgrade to the latest package version", FocusArea.dependencies),
        ("Sanitize user input", "Prevent a SQL injection vulnerability", FocusArea.security),
        ("Reduce query latency", "Optimize the slow N+1 query", FocusArea.performance),
        ("Remove dead code", "Refactor duplicate logic for cleanup", FocusArea.code_cleanup),
    ],
)
def test_classify_focus_areas_matches_expected_keyword(title: str, description: str, expected: FocusArea) -> None:
    task = _task("t1", title, description)
    assert expected in classify_focus_areas(task)


def test_classify_focus_areas_falls_back_to_code_cleanup_for_ungrounded_repository_analysis() -> None:
    task = _task(
        "t1", "Normalize path separators", "Ensure consistent behavior across platforms",
        source="repository-analysis",
    )
    assert classify_focus_areas(task) == {FocusArea.code_cleanup}


def test_classify_focus_areas_falls_back_to_major_features_for_an_unclassifiable_ai_proposal() -> None:
    task = _task("t1", "Do something interesting", "No concrete signal here", source="llm-backlog")
    assert classify_focus_areas(task) == {FocusArea.major_features}


# -- select_task_for_autopilot -------------------------------------------------------------


def test_select_task_for_autopilot_picks_the_first_matching_backlog_task() -> None:
    tasks = [
        _task("t1", "Implement a new dashboard", "brand new feature"),  # major_features, excluded by default
        _task("t2", "Fix crash on startup", "unhandled error"),  # bug_fixes, allowed
        _task("t3", "Add unit tests for parser"),  # tests, allowed but lower priority in list order
    ]

    chosen = select_task_for_autopilot(tasks, [FocusArea.bug_fixes, FocusArea.tests])

    assert chosen is not None
    assert chosen.id == "t2"


def test_select_task_for_autopilot_returns_none_when_nothing_matches() -> None:
    tasks = [_task("t1", "Implement a brand new major feature")]

    assert select_task_for_autopilot(tasks, [FocusArea.bug_fixes]) is None


def test_select_task_for_autopilot_returns_none_when_no_focus_areas_are_allowed() -> None:
    tasks = [_task("t1", "Fix crash on startup")]

    assert select_task_for_autopilot(tasks, []) is None


def test_select_task_for_autopilot_ignores_tasks_not_in_backlog_status() -> None:
    task = Task(
        id="t1", title="Fix crash on startup", description="", priority=3, risk=RiskLevel.low,
        source="repository-todo", status=TaskStatus.approved,
    )

    assert select_task_for_autopilot([task], [FocusArea.bug_fixes]) is None
