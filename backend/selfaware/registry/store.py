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
from selfaware.events.payloads import DriverRegisteredPayload, DriverSummary, DriverUpdatedPayload
from selfaware.events.types import DriverStatus, EventType, ProtocolClass
from selfaware.registry.models import DriverRecord

if TYPE_CHECKING:
    from selfaware.hardware.session import BoardSession


def code_hash(code: str) -> str:
    """Short content address for driver source — the UI's 'did it change' tell."""
    return hashlib.sha256(code.encode()).hexdigest()[:12]


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

    # --- PR3 seam ---------------------------------------------------------------------

    def as_toolset(self, session: "BoardSession") -> Any:
        """PR3: FunctionToolset with call-time registry resolution.

        Build-day job: return a pydantic-ai FunctionToolset whose read_<slug>/
        set_<slug> functions close over ONLY the slug and look the record up
        from THIS registry at call time (status must be ACTIVE, else
        ModelRetry('not commissioned')), exec through `session` (never the raw
        transport), and parse via bringup.harness. The copilot attaches it via
        a dynamic @agent.toolset so hot-swaps and new admissions appear on the
        very next agent step.
        """
        raise NotImplementedError("PR3: FunctionToolset with call-time registry resolution")
