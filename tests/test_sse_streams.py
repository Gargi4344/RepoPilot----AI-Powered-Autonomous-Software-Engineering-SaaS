import asyncio

import pytest

from app import main as main_module
from app.models import RunEvent


def test_run_event_stream_sends_keepalive_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a run step that legitimately produces zero events for several minutes (a
    # slow `npm install` during a baseline check, observed in production) left an SSE
    # connection completely silent for that whole window -- indistinguishable from a dead
    # connection to any layer with an idle timeout, and with nothing to trigger the
    # browser's EventSource to reconnect. A short keepalive interval proves the stream keeps
    # writing to the response even when no real event is available yet.
    monkeypatch.setattr(main_module, "_SSE_KEEPALIVE_SECONDS", 0.05)

    async def scenario() -> str:
        gen = main_module._run_event_stream("no-such-run-id")
        try:
            return await asyncio.wait_for(gen.__anext__(), timeout=2)
        finally:
            await gen.aclose()

    frame = asyncio.run(scenario())
    assert frame == ": keep-alive\n\n"


def test_global_event_stream_sends_keepalive_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unlike the per-run stream (scoped to a run_id no other test has touched), the global
    # stream replays db.list_recent_events() across every run in the shared test database --
    # by the time this runs alongside the rest of the suite, that history is very likely
    # non-empty. Drain whatever history happens to be there first; this test only cares
    # about what happens once that replay is exhausted and the stream is genuinely idle.
    monkeypatch.setattr(main_module, "_SSE_KEEPALIVE_SECONDS", 0.05)

    async def scenario() -> str:
        gen = main_module._global_event_stream()
        try:
            frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
            while "run-event" in frame:
                frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
            return frame
        finally:
            await gen.aclose()

    frame = asyncio.run(scenario())
    assert frame == ": keep-alive\n\n"


def test_run_event_stream_delivers_a_real_event_without_waiting_for_the_keepalive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The keepalive interval is set generously long here specifically to prove a real,
    # published event wakes the stream up immediately -- it must not have to wait out a full
    # keepalive cycle to be delivered.
    monkeypatch.setattr(main_module, "_SSE_KEEPALIVE_SECONDS", 5)
    run_id = "run-for-sse-delivery-test"

    async def scenario() -> str:
        gen = main_module._run_event_stream(run_id)
        next_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)  # let the generator reach queue.get() before publishing
        # Published directly (not via db.add_event) -- run_events has a foreign key on a
        # real runs row, and this test only cares about EventBus delivery through the
        # stream, not persistence.
        event = RunEvent(id=1, run_id=run_id, ts="2026-01-01T00:00:00+00:00", phase="coding", level="info", message="hello")
        await main_module.event_bus.publish(run_id, event)
        try:
            return await asyncio.wait_for(next_task, timeout=1)
        finally:
            await gen.aclose()

    frame = asyncio.run(scenario())
    assert "run-event" in frame
    assert "hello" in frame
