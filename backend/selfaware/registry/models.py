"""Registry domain models.

DriverStatus is OWNED by the event contract (its values ride payloads); this
module RE-EXPORTS it as the domain-side import point — same pattern as
bringup/models.py. DriverSummary is likewise the events.payloads model:
`DriverRecord.summary()` converts, so hello-rehydration and REST responses
can never drift from the wire contract.
"""

from datetime import datetime

from pydantic import BaseModel

from selfaware.events.payloads import DriverSummary
from selfaware.events.types import DriverStatus, ProtocolClass

__all__ = ["DriverRecord", "DriverStatus", "DriverSummary", "ProtocolClass"]


class DriverRecord(BaseModel):
    """One commissioned (or commissioning) device, server-side truth.

    driver_code is the exact source that PASSED on real silicon — the poller,
    read tools, and the REST 'view source' panel all run/show precisely this
    text, never a variant.
    """

    slug: str
    display_name: str
    protocol_class: ProtocolClass
    driver_code: str
    pins: dict[str, int]
    unit: str = ""
    status: DriverStatus = DriverStatus.COMMISSIONING
    verified_at: datetime | None = None
    attempts_used: int = 0
    last_reading: float | None = None
    last_read_at: datetime | None = None

    def summary(self) -> DriverSummary:
        """Wire-friendly subset for system.hello rehydration (the contract model)."""
        return DriverSummary(
            slug=self.slug,
            display_name=self.display_name,
            protocol_class=self.protocol_class,
            status=self.status,
            unit=self.unit,
            last_reading=self.last_reading,
        )

    @property
    def tool_names(self) -> list[str]:
        """The capabilities this record arms: set_<slug> for outputs, read_<slug> otherwise."""
        if self.protocol_class is ProtocolClass.OUTPUT:
            return [f"set_{self.slug}"]
        return [f"read_{self.slug}"]

    # --- shared tool-description wording -------------------------------------
    # Single source of truth for both the copilot's in-process toolset
    # (registry/store.py::as_toolset) and the out-of-process MCP transport
    # (mcp_server.py) — an external agent and the copilot should never see
    # different descriptions for the same verified capability.

    def read_description(self) -> str:
        unit = f" (unit: {self.unit})" if self.unit else ""
        return f"Take a live reading from {self.display_name}{unit} via its verified on-board driver."

    def set_description(self) -> str:
        return f"Set {self.display_name} to a level (0 = off) via its verified on-board driver."
