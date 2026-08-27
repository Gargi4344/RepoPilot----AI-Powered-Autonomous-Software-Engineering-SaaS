from __future__ import annotations

import asyncio
from collections import defaultdict

from app.models import RunEvent


class EventBus:
    """In-process pub/sub that fans each RunEvent out to any live SSE subscribers
    (per-run and global) as it happens. Not persisted itself -- app.db is the durable
    store; this only carries live updates to already-connected clients."""

    def __init__(self) -> None:
        self._run_subscribers: dict[str, list[asyncio.Queue[RunEvent]]] = defaultdict(list)
        self._global_subscribers: list[asyncio.Queue[RunEvent]] = []

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent]:
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._run_subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent]) -> None:
        subscribers = self._run_subscribers.get(run_id)
        if subscribers and queue in subscribers:
            subscribers.remove(queue)

    def subscribe_global(self) -> asyncio.Queue[RunEvent]:
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._global_subscribers.append(queue)
        return queue

    def unsubscribe_global(self, queue: asyncio.Queue[RunEvent]) -> None:
        if queue in self._global_subscribers:
            self._global_subscribers.remove(queue)

    async def publish(self, run_id: str, event: RunEvent) -> None:
        for queue in self._run_subscribers.get(run_id, []):
            await queue.put(event)
        for queue in self._global_subscribers:
            await queue.put(event)
