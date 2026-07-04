"""In-process event bus: single writer discipline, per-subscriber fan-out.

The bus is the ONLY place envelopes are built: it stamps v/ts/seq, so seq is
globally ordered per process and the UI can trust it. Subscribers (one per
websocket) each get a bounded queue; when a queue is full the OLDEST event is
dropped for that subscriber — a slow browser tab must never backpressure the
commission loop. system.hello rehydrates state on reconnect, so drops are safe.
"""

import asyncio
import itertools
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from pydantic import BaseModel

from selfaware.events.envelope import Event
from selfaware.events.types import EventType

DEFAULT_QUEUE_SIZE = 256


class Subscription:
    """One subscriber's view of the stream. Async-iterable; never blocks the bus."""

    def __init__(self, maxsize: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)

    def _offer(self, event: Event) -> None:
        """Enqueue without blocking; on a full queue, drop the oldest event."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()  # sacrifice the oldest
            except asyncio.QueueEmpty:  # pragma: no cover - race window only
                pass
            self._queue.put_nowait(event)

    def __aiter__(self) -> AsyncIterator[Event]:
        return self

    async def __anext__(self) -> Event:
        return await self._queue.get()


class EventBus:
    """Fan-out hub. publish() is synchronous and never awaits — safe to call
    from any coroutine (commission loop, poller, handlers) without yielding."""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._subscribers: set[Subscription] = set()
        self._seq = itertools.count(1)
        self._queue_size = queue_size

    def subscribe(self) -> Subscription:
        sub = Subscription(maxsize=self._queue_size)
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)

    def publish(self, type: EventType | str, payload: BaseModel) -> Event:
        """Stamp the envelope (v/ts/seq) and offer to every subscriber.

        Returns the stamped Event (useful for logging/tests). Fire-and-forget:
        a subscriber's slowness costs that subscriber its oldest events, never
        the publisher any time.
        """
        event = Event(
            type=str(type),
            ts=datetime.now(UTC),
            seq=next(self._seq),
            payload=payload.model_dump(mode="json"),
        )
        for sub in self._subscribers:
            sub._offer(event)
        return event

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
