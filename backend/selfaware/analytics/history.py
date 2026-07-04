"""Per-slug reading history — the time series analytics/health.py reasons over.

Populated by subscribing to the EventBus for SENSOR_READING (the same event
the poller and every WS client already see) — no new wiring into the
hardware path, no second copy of the read logic. In-memory only, bounded per
slug: a restart honestly forgets, same posture as the registry itself.

Also clears a slug's series on a (re-)commission — a physically different
device may now be wired to the same pins, so the old series must not be
silently blended with the new one. This is DRIVER_REGISTERED for a slug's
very first commission, but bringup/loop.py::_admit() only calls register()
once per slug ever — every subsequent commission of an EXISTING slug goes
through registry.update_code(reason="recommission"), publishing
DRIVER_UPDATED instead (confirmed by running the real loop, not just the
unit tests, which called register() directly and never exercised this
path). So both trigger a clear; only reason="repair" does not, since that's
the same physical sensor with patched code — its prior readings are still
valid context. ("repair" isn't emitted anywhere in the codebase today, but
the reason field's contract already documents it, so honoring the
distinction costs nothing and holds if that path is ever wired up.)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from selfaware.events.bus import EventBus
from selfaware.events.payloads import DriverRegisteredPayload, DriverUpdatedPayload, SensorReadingPayload
from selfaware.events.types import EventType

logger = logging.getLogger("selfaware.analytics.history")

Point = tuple[float, float]  # (unix_ts, value)

DEFAULT_CAPACITY = 2000  # ample for several days even at a 1/min poll interval


def _is_finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")  # NaN != NaN; inf check by magnitude


@dataclass
class _Series:
    capacity: int
    points: deque[Point] = field(default_factory=deque)

    def append(self, point: Point) -> None:
        self.points.append(point)
        while len(self.points) > self.capacity:
            self.points.popleft()


class HistoryStore:
    """One subscription, fanned out into per-slug bounded series."""

    def __init__(self, bus: EventBus, capacity: int = DEFAULT_CAPACITY) -> None:
        self._bus = bus
        self._capacity = capacity
        self._series: dict[str, _Series] = {}

    def series(self, slug: str) -> list[Point]:
        s = self._series.get(slug)
        return list(s.points) if s else []

    def seed(self, slug: str, points: list[Point]) -> None:
        """Backfill replayed/test history for a slug with no real data yet.

        Not used anywhere in the live app — the product shows real history
        only, however sparse. Kept for tests that need deterministic series
        without waiting on the bus.
        """
        series = self._series.setdefault(slug, _Series(capacity=self._capacity))
        for point in points:
            series.append(point)

    def _on_reading(self, payload: SensorReadingPayload) -> None:
        if not _is_finite(payload.value):
            logger.warning("history: dropping non-finite reading for %s: %r", payload.slug, payload.value)
            return
        series = self._series.setdefault(payload.slug, _Series(capacity=self._capacity))
        series.append((time.time(), payload.value))

    def _clear(self, slug: str) -> None:
        self._series.pop(slug, None)

    async def run(self) -> None:
        """Background task: drain the bus subscription forever, one bad
        event at a time — a single malformed payload must not end tracking
        for every other slug for the rest of the process's life."""
        sub = self._bus.subscribe()
        try:
            async for event in sub:
                try:
                    if event.type == str(EventType.SENSOR_READING):
                        self._on_reading(SensorReadingPayload.model_validate(event.payload))
                    elif event.type == str(EventType.DRIVER_REGISTERED):
                        self._clear(DriverRegisteredPayload.model_validate(event.payload).slug)
                    elif event.type == str(EventType.DRIVER_UPDATED):
                        updated = DriverUpdatedPayload.model_validate(event.payload)
                        if updated.reason == "recommission":
                            self._clear(updated.slug)
                except Exception:  # noqa: BLE001 — one bad event must not kill the listener
                    logger.exception("history: skipping unparseable %s event", event.type)
        finally:
            self._bus.unsubscribe(sub)
