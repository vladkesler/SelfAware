"""CommissionService — the single entry point for starting a commission.

BOTH callers go through enqueue(): the cmd.commission handler (api/handlers,
PR3) and the copilot's commission_sensor tool (agents/copilot, PR3). That is
what makes the single-flight guard airtight — there is exactly one door.

Single-flight: one commission at a time, ever. The board has one wire and the
demo has one narrative; a second enqueue while one runs is rejected loudly
with system.error{code:"commission_busy"}, never queued silently.
"""

import asyncio
import functools
from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from selfaware.bringup.loop import CommissionRunner
from selfaware.bringup.models import BringupSpec, CommissionResult, CommissionStatus, ProtocolClass
from selfaware.events.bus import EventBus
from selfaware.events.payloads import CommissionCommand, ErrorPayload
from selfaware.events.types import EventType

if TYPE_CHECKING:
    from selfaware.config import Settings
    from selfaware.memory.client import MemoryClient

# Terminal outcomes kept for status() polling. A small ring, not a database:
# the single-flight guard means at most one commission at a time, and a poller
# only ever cares about recent ids.
_OUTCOME_RING_CAP = 16


class SpecResolutionError(Exception):
    """A commission request that can't become a BringupSpec — carries the same
    error codes the WS handler publishes (unknown_preset / bad_spec) so both
    doors speak one vocabulary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_spec(payload: CommissionCommand, settings: "Settings") -> BringupSpec:
    """CommissionCommand -> BringupSpec: a one-click preset or a full spec.

    Shared by the WS cmd.commission handler and POST /api/commission — one
    resolution, one vocabulary of failures.
    """
    if payload.preset_slug:
        spec = next((s for s in settings.default_specs() if s.slug == payload.preset_slug), None)
        if spec is None:
            raise SpecResolutionError("unknown_preset", f"no preset named {payload.preset_slug!r}")
        return spec
    if not (payload.slug and payload.protocol_class and payload.pins):
        raise SpecResolutionError("bad_spec", "full spec needs at least slug, protocol_class and pins")
    return BringupSpec(
        slug=payload.slug,
        display_name=payload.display_name or payload.slug,
        protocol_class=payload.protocol_class,
        pins=payload.pins,
        i2c_addr=payload.i2c_addr,
        expected_min=payload.expected_min,
        expected_max=payload.expected_max,
        unit=payload.unit,
        stimulus_hint=payload.stimulus_hint,
        verify_with_slug=payload.verify_with_slug,
        extra_context=payload.extra_context,
    )


class CommissionService:
    def __init__(self, runner: CommissionRunner, bus: EventBus, memory: "MemoryClient | None" = None) -> None:
        self._runner = runner
        self._bus = bus
        self._memory = memory  # optional: passes are remembered fire-and-forget
        self._current: asyncio.Task[object] | None = None
        self._current_slug: str | None = None
        self._current_id: str | None = None
        self._outcomes: OrderedDict[str, dict[str, Any]] = OrderedDict()  # ring, newest last
        self._memory_tasks: set[asyncio.Task[None]] = set()  # keep refs so writes aren't GC'd

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
        self._current_id = commission_id
        self._current = asyncio.create_task(
            self._runner.run(spec, commission_id), name=f"commission-{spec.slug}"
        )
        # commission_id/slug ride the partial, NOT self._current_*: a task can be
        # done() (so a new enqueue succeeds and overwrites those) before its
        # done-callback actually runs.
        self._current.add_done_callback(functools.partial(self._on_done, commission_id, spec.slug))
        return commission_id

    def status(self, commission_id: str) -> dict[str, Any] | None:
        """Poll-shaped view of one commission: a stored terminal outcome, a
        'running' marker for the in-flight id, or None (-> the caller's 404)."""
        outcome = self._outcomes.get(commission_id)
        if outcome is not None:
            return outcome
        if commission_id == self._current_id and self.running:
            return {"commission_id": commission_id, "slug": self._current_slug, "status": "running"}
        return None

    def _record_outcome(self, commission_id: str, outcome: dict[str, Any]) -> None:
        self._outcomes[commission_id] = outcome
        while len(self._outcomes) > _OUTCOME_RING_CAP:
            self._outcomes.popitem(last=False)

    @staticmethod
    def _serialize(commission_id: str, result: CommissionResult) -> dict[str, Any]:
        """CommissionResult -> the status() wire shape. Attempts ride along in
        full (verbatim tracebacks included) — the honest post-mortem is the point."""
        spec = result.spec
        passed = result.status is CommissionStatus.PASSED
        tool = None
        if passed:
            tool = f"set_{spec.slug}" if spec.protocol_class is ProtocolClass.OUTPUT else f"read_{spec.slug}"
        return {
            "commission_id": commission_id,
            "slug": spec.slug,
            "display_name": spec.display_name,
            "status": result.status.value,
            "attempts_used": len(result.attempts),
            "final_reading": result.final_reading,
            "unit": spec.unit,
            "failure_reason": result.failure_reason,
            "attempts": [a.model_dump(mode="json") for a in result.attempts],
            "tool": tool,
        }

    def _on_done(self, commission_id: str, slug: str, task: asyncio.Task[object]) -> None:
        """A crashed runner must be loud (the runner itself only emits honest
        commission.failed on BUDGET exhaustion — an unexpected exception here
        is a bug, and swallowing it would fake liveness)."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._record_outcome(
                commission_id,
                {
                    "commission_id": commission_id,
                    "slug": slug,
                    "status": "crashed",
                    "failure_reason": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            self._bus.publish(
                EventType.SYSTEM_ERROR,
                ErrorPayload(
                    code="commission_crash",
                    message=f"commission for {slug!r} crashed: {exc}",
                    detail=type(exc).__name__,
                ),
            )
            return
        result = task.result()
        if isinstance(result, CommissionResult):
            self._record_outcome(commission_id, self._serialize(commission_id, result))
        if self._memory is not None and isinstance(result, CommissionResult) and result.status is CommissionStatus.PASSED:
            # Fire-and-forget: a slow/absent memory server never blocks anything.
            memory_task = asyncio.create_task(self._remember_pass(result), name=f"memory-{result.spec.slug}")
            self._memory_tasks.add(memory_task)
            memory_task.add_done_callback(self._memory_tasks.discard)

    async def _remember_pass(self, result: CommissionResult) -> None:
        """Memory write sites for a pass: kind=driver always, kind=repair_lesson
        when it took more than one attempt (the loop's compounding asset)."""
        assert self._memory is not None
        spec = result.spec
        try:
            await self._memory.remember(
                kind="driver",
                text=(
                    f"Working {spec.protocol_class.value} driver for {spec.display_name} "
                    f"({spec.slug}) on pins {spec.pins}:\n{result.final_code or ''}"
                ),
                meta={"slug": spec.slug, "protocol_class": spec.protocol_class.value, "pins": spec.pins},
            )
            if len(result.attempts) > 1:
                failures = [
                    a.gate_reason or a.traceback or "implausible reading"
                    for a in result.attempts
                    if not a.passed
                ]
                await self._memory.remember(
                    kind="repair_lesson",
                    text=(
                        f"Commissioning {spec.slug} ({spec.protocol_class.value}) took "
                        f"{len(result.attempts)} attempts. Failures on the way: "
                        + " | ".join(failures)
                    ),
                    meta={"slug": spec.slug, "attempts_used": len(result.attempts)},
                )
        except Exception:  # noqa: BLE001 — memory is a witness, never a failure source
            pass
