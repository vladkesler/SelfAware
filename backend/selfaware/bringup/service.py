"""CommissionService — the single entry point for starting a commission.

BOTH callers go through enqueue(): the cmd.commission handler (api/handlers,
PR3) and the copilot's commission_sensor tool (agents/copilot, PR3). That is
what makes the single-flight guard airtight — there is exactly one door.

Single-flight: one commission at a time, ever. The board has one wire and the
demo has one narrative; a second enqueue while one runs is rejected loudly
with system.error{code:"commission_busy"}, never queued silently.
"""

import asyncio
from uuid import uuid4

from selfaware.bringup.loop import CommissionRunner
from selfaware.bringup.models import BringupSpec
from selfaware.events.bus import EventBus
from selfaware.events.payloads import ErrorPayload
from selfaware.events.types import EventType


class CommissionService:
    def __init__(self, runner: CommissionRunner, bus: EventBus) -> None:
        self._runner = runner
        self._bus = bus
        self._current: asyncio.Task[object] | None = None
        self._current_slug: str | None = None

    @property
    def running(self) -> bool:
        return self._current is not None and not self._current.done()

    def enqueue(self, spec: BringupSpec) -> str | None:
        """Start a commission in the background; returns its commission_id.

        Returns None (after publishing system.error{commission_busy}) when a
        commission is already in flight — callers surface that, they never
        wait. The background task owns the run; CommissionRunner.run emits
        every commission.* event including the terminal passed/failed, so
        nothing here needs to await it.
        """
        if self.running:
            self._bus.publish(
                EventType.SYSTEM_ERROR,
                ErrorPayload(
                    code="commission_busy",
                    message=f"a commission is already running ({self._current_slug}); one at a time",
                ),
            )
            return None
        commission_id = uuid4().hex
        self._current_slug = spec.slug
        self._current = asyncio.create_task(
            self._runner.run(spec, commission_id), name=f"commission-{spec.slug}"
        )
        self._current.add_done_callback(self._on_done)
        return commission_id

    def _on_done(self, task: asyncio.Task[object]) -> None:
        """A crashed runner must be loud (the runner itself only emits honest
        commission.failed on BUDGET exhaustion — an unexpected exception here
        is a bug, and swallowing it would fake liveness)."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._bus.publish(
                EventType.SYSTEM_ERROR,
                ErrorPayload(
                    code="commission_crash",
                    message=f"commission for {self._current_slug!r} crashed: {exc}",
                    detail=type(exc).__name__,
                ),
            )
