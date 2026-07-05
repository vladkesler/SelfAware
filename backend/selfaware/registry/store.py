"""DriverRegistry — in-memory store with the admission gate and hot-swap.

ADMISSION GATE (invariant #6): register() is called ONLY by the
CommissionRunner after a real on-board pass. Nothing else may add a record,
so every registered driver — and therefore every tool the copilot holds — is
backed by code that verified on silicon. A driver that never passed simply
does not exist here.

Hot-swap: update_code() replaces driver_code in place and emits
driver.updated. Because tools resolve records at CALL time (as_toolset, PR3),
the very next tool call runs the new code under the same stable tool name.
"""

from __future__ import annotations  # `def list()` below shadows builtins.list in class-body annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from selfaware.events.bus import EventBus
from selfaware.events.payloads import (
    ActuatorStatePayload,
    DriverRegisteredPayload,
    DriverSummary,
    DriverUpdatedPayload,
    SensorReadingPayload,
)
from selfaware.events.types import DriverStatus, EventType, ProtocolClass
from selfaware.registry.models import DriverRecord

if TYPE_CHECKING:
    from selfaware.hardware.session import BoardSession


def code_hash(code: str) -> str:
    """Short content address for driver source — the UI's 'did it change' tell."""
    return hashlib.sha256(code.encode()).hexdigest()[:12]


class DriverToolError(Exception):
    """A registry-mediated board call failed, with an honest reason.

    One exception type for both consumers: the copilot toolset re-raises it
    as ModelRetry (the model self-corrects), cmd.read/cmd.set handlers map it
    to system.error (the human sees the same words).
    """


class DriverRegistry:
    """In-memory dict keyed by slug. JSON snapshot to settings.sqlite_path is a
    build-day nicety; day-1 a restart honestly forgets (re-commission)."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._records: dict[str, DriverRecord] = {}

    # --- admission + hot-swap ----------------------------------------------------

    def register(self, record: DriverRecord) -> None:
        """Admit a driver that just PASSED on the board. Emits driver.registered.

        Caller contract: only the CommissionRunner, only after plausibility
        passed. Overwrites any prior record for the slug (a re-commission).
        """
        self._records[record.slug] = record
        self._bus.publish(
            EventType.DRIVER_REGISTERED,
            DriverRegisteredPayload(
                slug=record.slug,
                display_name=record.display_name,
                protocol_class=record.protocol_class,
                pins=record.pins,
                tool_names=record.tool_names,
                code_hash=code_hash(record.driver_code),
                unit=record.unit,
            ),
        )

    def update_code(self, slug: str, code: str, verified_at: datetime | None = None, reason: str = "repair") -> None:
        """Hot-swap a registered driver's source. Emits driver.updated.

        reason: 'repair' | 'recommission' (wire vocabulary of DriverUpdatedPayload).
        Raises KeyError for an unknown slug — hot-swapping a driver that never
        passed would launder code past the admission gate.
        """
        record = self._records.get(slug)
        if record is None:
            raise KeyError(f"cannot update unregistered driver {slug!r} (admission gate)")
        record.driver_code = code
        record.verified_at = verified_at or datetime.now(UTC)
        record.status = DriverStatus.ACTIVE
        self._bus.publish(
            EventType.DRIVER_UPDATED,
            DriverUpdatedPayload(slug=slug, code_hash=code_hash(code), reason=reason),
        )

    # --- lookups --------------------------------------------------------------------

    def get(self, slug: str) -> DriverRecord | None:
        return self._records.get(slug)

    def list(self) -> list[DriverRecord]:
        return list(self._records.values())

    def sensors(self) -> list[DriverRecord]:
        """ACTIVE non-output drivers — what the telemetry poller iterates."""
        return [
            r
            for r in self._records.values()
            if r.status is DriverStatus.ACTIVE and r.protocol_class is not ProtocolClass.OUTPUT
        ]

    def actuators(self) -> list[DriverRecord]:
        return [
            r
            for r in self._records.values()
            if r.status is DriverStatus.ACTIVE and r.protocol_class is ProtocolClass.OUTPUT
        ]

    def summaries(self) -> list[DriverSummary]:
        """Wire-shape list for system.hello rehydration."""
        return [r.summary() for r in self._records.values()]

    # --- live board access through verified drivers ------------------------------------

    async def perform_read(self, session: "BoardSession", slug: str) -> float:
        """Run <slug>'s verified driver on the board and publish sensor.reading.

        Resolves the record AT CALL TIME (hot-swap invariant #6) and execs via
        `session` (never the raw transport, invariant #3). Raises
        DriverToolError with an honest reason on every failure path — the
        toolset converts that to ModelRetry, cmd.read to system.error.
        """
        from selfaware.bringup import harness  # local: registry must import without bringup at module load

        record = self._active(slug)
        result = await session.exec(harness.build_read_payload(record.driver_code))
        if result.timed_out:
            raise DriverToolError(f"read_{slug}: host timeout — board soft-reset, try again")
        if result.stderr:
            raise DriverToolError(f"read_{slug}: board raised:\n{result.stderr}")
        try:
            value = harness.parse_reading(result)
        except harness.ReadingParseError as exc:
            raise DriverToolError(f"read_{slug}: {exc}") from exc
        record.last_reading = value
        record.last_read_at = datetime.now(UTC)
        self._bus.publish(
            EventType.SENSOR_READING,
            SensorReadingPayload(slug=slug, value=value, unit=record.unit, plausible=True),
        )
        return value

    async def perform_set(self, session: "BoardSession", slug: str, level: float) -> None:
        """Drive <slug>'s actuator to `level` and publish actuator.state.

        The payload guarantees set(0) on error IN THE SAME EXEC (stateful
        outputs latch), then re-raises so stderr stays the verbatim signal.
        actuator.state{ok=False} is published before DriverToolError raises.
        """
        record = self._active(slug)
        code = record.driver_code.rstrip("\n")
        payload = (
            f"{code}\n"
            "_act = Driver()\n"
            "try:\n"
            f"    _act.set({level!r})\n"
            f"    print({level!r})\n"
            "except Exception:\n"
            "    _act.set(0)\n"
            "    raise\n"
        )
        result = await session.exec(payload)
        ok = result.ok
        self._bus.publish(EventType.ACTUATOR_STATE, ActuatorStatePayload(slug=slug, level=level, ok=ok))
        if result.timed_out:
            raise DriverToolError(f"set_{slug}: host timeout — board soft-reset")
        if result.stderr:
            raise DriverToolError(f"set_{slug}: board raised (output forced back to 0):\n{result.stderr}")

    def _active(self, slug: str) -> DriverRecord:
        record = self._records.get(slug)
        if record is None or record.status is not DriverStatus.ACTIVE:
            raise DriverToolError(f"{slug!r} is not commissioned (no verified driver in the registry)")
        return record

    # --- the copilot's live toolset -----------------------------------------------------

    def as_toolset(self, session: "BoardSession") -> Any:
        """FunctionToolset of read_<slug>/set_<slug> for every ACTIVE driver.

        Rebuilt per agent step (the copilot attaches this via a dynamic
        @agent.toolset), and each closure captures ONLY the slug — perform_*
        re-resolves the record at call time, so a repair hot-swaps the
        implementation under a stable tool name and a driver demoted from
        ACTIVE answers ModelRetry('not commissioned') instead of running
        stale code.
        """
        from pydantic_ai import FunctionToolset, ModelRetry

        toolset: Any = FunctionToolset(id="commissioned")

        def _make_read(slug: str):
            async def read_tool() -> float:
                try:
                    return await self.perform_read(session, slug)
                except DriverToolError as exc:
                    raise ModelRetry(str(exc)) from exc

            return read_tool

        def _make_set(slug: str):
            async def set_tool(level: float) -> str:
                try:
                    await self.perform_set(session, slug, level)
                except DriverToolError as exc:
                    raise ModelRetry(str(exc)) from exc
                return f"{slug} set to {level:g}"

            return set_tool

        for record in self._records.values():
            if record.status is not DriverStatus.ACTIVE:
                continue  # admission gate: only silicon-verified drivers arm tools
            if record.protocol_class is ProtocolClass.OUTPUT:
                toolset.add_function(
                    _make_set(record.slug),
                    name=f"set_{record.slug}",
                    description=record.set_description(),
                )
            else:
                toolset.add_function(
                    _make_read(record.slug),
                    name=f"read_{record.slug}",
                    description=record.read_description(),
                )
        return toolset
