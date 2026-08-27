from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _analyze(client: TestClient, tmp_path: Path) -> int:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("# TODO: fix bug in handler\n")
    response = client.post("/api/v1/repositories/analyze", json={"path": str(tmp_path)})
    return response.json()["repository_id"]


def _plan_payload(**overrides) -> dict:
    payload = {
        "schedule_type": "daily",
        "run_time": "09:00",
        "timezone": "UTC",
        "focus_areas": ["bug_fixes", "tests"],
        "autonomy_level": "balanced",
        "max_runs_per_day": 1,
    }
    payload.update(overrides)
    return payload


def test_get_autopilot_before_configuration_returns_no_plan(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)

    response = client.get(f"/api/v1/repositories/{repository_id}/autopilot")

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] is None
    assert body["upcoming"] == []


def test_save_autopilot_activates_and_generates_a_bounded_schedule(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)

    response = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["status"] == "active"
    assert body["plan"]["autonomy_level"] == "balanced"
    assert 1 <= len(body["upcoming"]) <= 7
    assert all(sr["status"] == "scheduled" for sr in body["upcoming"])


def test_saving_again_replaces_settings_and_regenerates_upcoming_runs(tmp_path: Path) -> None:
    # Both saves use a daily schedule deliberately -- a weekly schedule's exact upcoming
    # count depends on which weekday "now" happens to be and whether today's run time has
    # already passed, which would make this test's outcome depend on when it happens to run.
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    first = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload(schedule_type="daily"))
    first_run_ids = {sr["id"] for sr in first.json()["upcoming"]}

    response = client.post(
        f"/api/v1/repositories/{repository_id}/autopilot",
        json=_plan_payload(schedule_type="daily", autonomy_level="conservative"),
    )

    body = response.json()
    assert body["plan"]["autonomy_level"] == "conservative"
    assert len(body["upcoming"]) >= 1
    # The old upcoming runs were cancelled and replaced with fresh ones, not just appended to.
    assert first_run_ids.isdisjoint({sr["id"] for sr in body["upcoming"]})


def test_pause_and_resume_autopilot(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())

    paused = client.post(f"/api/v1/repositories/{repository_id}/autopilot/pause")
    assert paused.json()["plan"]["status"] == "paused"

    resumed = client.post(f"/api/v1/repositories/{repository_id}/autopilot/resume")
    assert resumed.json()["plan"]["status"] == "active"


def test_pause_before_configuration_returns_404(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)

    response = client.post(f"/api/v1/repositories/{repository_id}/autopilot/pause")

    assert response.status_code == 404


def test_cancel_autopilot_cancels_the_plan_and_its_upcoming_runs(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    saved = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())
    upcoming_before = saved.json()["upcoming"]
    assert upcoming_before

    response = client.post(f"/api/v1/repositories/{repository_id}/autopilot/cancel")

    body = response.json()
    assert body["plan"]["status"] == "cancelled"
    assert body["upcoming"] == []


def test_cancel_a_single_scheduled_run(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    saved = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())
    scheduled_run_id = saved.json()["upcoming"][0]["id"]

    response = client.post(f"/api/v1/autopilot/scheduled-runs/{scheduled_run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Cancelling an already-cancelled run is rejected, not silently accepted again.
    again = client.post(f"/api/v1/autopilot/scheduled-runs/{scheduled_run_id}/cancel")
    assert again.status_code == 409


def test_reschedule_a_single_scheduled_run(tmp_path: Path) -> None:
    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    saved = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())
    scheduled_run_id = saved.json()["upcoming"][0]["id"]

    response = client.put(
        f"/api/v1/autopilot/scheduled-runs/{scheduled_run_id}", json={"scheduled_at": "2099-01-01T09:00:00+00:00"}
    )

    assert response.status_code == 200
    assert response.json()["scheduled_at"] == "2099-01-01T09:00:00+00:00"


def test_scheduled_run_endpoints_404_for_a_run_owned_by_another_user(tmp_path: Path) -> None:
    from app.auth import SessionUser
    from app.main import get_current_user

    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)
    saved = client.post(f"/api/v1/repositories/{repository_id}/autopilot", json=_plan_payload())
    scheduled_run_id = saved.json()["upcoming"][0]["id"]

    app.dependency_overrides[get_current_user] = lambda: SessionUser(
        login="someone-else", name=None, avatar_url=None, access_token="x"
    )
    try:
        response = client.post(f"/api/v1/autopilot/scheduled-runs/{scheduled_run_id}/cancel")
        assert response.status_code == 404
    finally:
        app.dependency_overrides[get_current_user] = lambda: SessionUser(
            login="test-user", name="Test User", avatar_url=None, access_token="test-access-token"
        )


def test_autopilot_endpoints_404_for_a_repository_owned_by_another_user(tmp_path: Path) -> None:
    from app.auth import SessionUser
    from app.main import get_current_user

    client = TestClient(app)
    repository_id = _analyze(client, tmp_path)

    app.dependency_overrides[get_current_user] = lambda: SessionUser(
        login="someone-else", name=None, avatar_url=None, access_token="x"
    )
    try:
        response = client.get(f"/api/v1/repositories/{repository_id}/autopilot")
        assert response.status_code == 404
    finally:
        app.dependency_overrides[get_current_user] = lambda: SessionUser(
            login="test-user", name="Test User", avatar_url=None, access_token="test-access-token"
        )
