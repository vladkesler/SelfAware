"""HealthWatcher — the derived-verdict push, mirror of hardware/watcher.py.

Rides its own periodic task, but touches NO wire and NO lock: it reads the
in-memory HistoryStore series + the registry only, so it can run as often as
it likes without ever serializing against a commission or a tool call. It
publishes a sensor.health event ONLY when a driver's coarse verdict changes
(status or trend direction) — steady state is silent, the same diff-on-change
discipline as DiscoveryWatcher's I2C scan (so a healthy fleet doesn't flood
the bus every tick). On connect the /ws endpoint replays current_health() so a
late client rehydrates (reconnect == rehydrate, never replay), exactly like
discovery presences.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from selfaware.analytics.health import build_health_payload
from selfaware.analytics.history import HistoryStore
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.payloads import SensorHealthPayload
from selfaware.events.types import EventType
from selfaware.registry.store import DriverRegistry


class HealthWatcher:
    """Periodic health scoring over HistoryStore -> sensor.health on change."""

    def __init__(
        self,
        registry: DriverRegistry,
        history: HistoryStore,
        bus: EventBus,
        settings: Settings,
    ) -> None:
        self._registry = registry
        self._history = history
        self._bus = bus
        self._settings = settings
        self._interval_s = settings.health_interval_s
        # last PUBLISHED coarse verdict per slug (status, trend.direction), so a
        # reason string jittering by a decimal doesn't re-publish; a real
        # transition (healthy -> degrading -> critical) does.
        self._last: dict[str, tuple[str, ...]] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Spawn the watch task. Idempotent."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._watch_loop(), name="selfaware-health")

    async def stop(self) -> None:
        """Cancel + reap the watch task."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _watch_loop(self) -> None:
        while True:
            try:
                self._assess_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — health scoring must never kill itself
                pass
            await asyncio.sleep(self._interval_s)

    def _assess_all(self) -> list[SensorHealthPayload]:
        """Fresh verdict for every ACTIVE driver (sensors scored; actuators
        answered "not_monitored") — computed at call time from the live
        registry + history, never a cached snapshot."""
        now = time.time()
        interval = self._settings.poller_interval_s
        return [
            build_health_payload(record, self._history.series(record.slug), now=now, interval=interval)
            for record in (*self._registry.sensors(), *self._registry.actuators())
        ]

    def _assess_once(self) -> None:
        for payload in self._assess_all():
            sig = (payload.status, payload.trend.direction)
            # While still calibrating, let the baseline counter tick so the UI
            # shows real progress toward the first verdict; once a status lands,
            # only a genuine transition re-publishes.
            if payload.status == "unknown":
                sig = (*sig, str(payload.readings_count))
            if self._last.get(payload.slug) == sig:
                continue
            self._last[payload.slug] = sig
            self._bus.publish(EventType.SENSOR_HEALTH, payload)

    def current_health(self) -> list[SensorHealthPayload]:
        """Every active driver's current verdict — replayed on /ws connect."""
        return self._assess_all()
