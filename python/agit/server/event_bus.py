"""In-process event bus for real-time streaming of agit events."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agit.server.event_bus")


@dataclass
class AgitEvent:
    """An event emitted by the agit engine."""
    event_type: str  # commit_created, branch_created, merge_completed, etc.
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EventBus:
    """Async pub/sub event bus for SSE streaming."""

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: list[asyncio.Queue[AgitEvent]] = []
        self._history: list[AgitEvent] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    async def publish(self, event: AgitEvent) -> None:
        """Publish an event to all subscribers."""
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            dead_queues = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_queues.append(queue)

            for q in dead_queues:
                self._subscribers.remove(q)

        logger.debug("Published event: %s (subscribers: %d)", event.event_type, len(self._subscribers))

    async def subscribe(self, max_queue: int = 256) -> asyncio.Queue[AgitEvent]:
        """Create a subscription queue."""
        queue: asyncio.Queue[AgitEvent] = asyncio.Queue(maxsize=max_queue)
        async with self._lock:
            self._subscribers.append(queue)
        logger.info("New subscriber (total: %d)", len(self._subscribers))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[AgitEvent]) -> None:
        """Remove a subscription."""
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
        logger.info("Subscriber removed (total: %d)", len(self._subscribers))

    async def events_since(self, offset: int = 0) -> list[AgitEvent]:
        """Get events from offset onwards."""
        async with self._lock:
            return list(self._history[offset:])

    @property
    def event_count(self) -> int:
        return len(self._history)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Global singleton
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
