"""One Pydantic model per event/command payload — THE frontend contract.

Mirrored by hand in `frontend/src/types/events.ts`, documented in
`docs/event-protocol.md`. Keep all three in lockstep.

Conventions (post design-critique, canonical):
  * commission.* payloads all carry commission_id for client-side correlation.
  * agent.* payloads all carry `agent` — an AgentId value ("author"|"medic"|"pilot").
  * traceback fields are VERBATIM board stderr — never trimmed or re-wrapped.
  * driver.* payloads are FLAT (no nested DriverSummary in the event itself;
    the summary model is used in system.hello's rehydration list).
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from selfaware.events.types import (
    CommissionStage,
    DriverStatus,
    ProtocolClass,
    StageStatus,
)

# --- shared wire models ------------------------------------------------------


class BoardStatusPayload(BaseModel):
    """Also the payload of board.status. Frontend derives its state enum."""

    connected: bool
    port_id: str | None = None
    mock: bool = False
    busy: bool = False  # true while a commission holds the exclusive lock


class DriverSummary(BaseModel):
    """Wire-friendly driver subset for system.hello rehydration."""

    slug: str
    display_name: str
    protocol_class: ProtocolClass
    status: DriverStatus
    unit: str = ""
    last_reading: float | None = None


# --- system.* ----------------------------------------------------------------


class HelloPayload(BaseModel):
    """First frame on every connection: full state, so reconnect == rehydrate."""

    server_version: str
    protocol_v: int
    model: str = ""  # the provider:model the agents run on, surfaced in the fascia
    board: BoardStatusPayload
    drivers: list[DriverSummary]


class AckPayload(BaseModel):
    cmd_id: UUID


class ErrorPayload(BaseModel):
    code: str  # machine-readable: unknown_command | model_unavailable | board_offline | ...
    message: str
    cmd_id: UUID | None = None
    detail: str | None = None


# --- board.* -----------------------------------------------------------------


class BoardConnectedPayload(BaseModel):
    port_id: str
    mock: bool


class BoardDisconnectedPayload(BaseModel):
    reason: str


# --- commission.* ------------------------------------------------------------


class CommissionStartedPayload(BaseModel):
    commission_id: str
    slug: str
    display_name: str
    protocol_class: ProtocolClass
    pins: dict[str, int]  # role -> GPIO, e.g. {"adc": 27} | {"trig": 14, "echo": 15}
    max_attempts: int


class CommissionStagePayload(BaseModel):
    commission_id: str
    attempt: int
    stage: CommissionStage
    status: StageStatus
    detail: str = ""


class CommissionCodePayload(BaseModel):
    commission_id: str
    attempt: int
    code: str  # full generated MicroPython source, verbatim, pre-gate
    is_repair: bool = False  # True when regenerated with the previous verbatim error in hand


class CommissionTracebackPayload(BaseModel):
    commission_id: str
    attempt: int
    stage: CommissionStage
    traceback: str  # VERBATIM — the UI renders it raw, the repair prompt embeds it untouched


class CommissionPassedPayload(BaseModel):
    commission_id: str
    slug: str
    attempts_used: int
    reading: float | None = None
    unit: str = ""


class CommissionFailedPayload(BaseModel):
    commission_id: str
    slug: str
    attempts_used: int
    reason: str
    last_traceback: str | None = None


# --- agent.* -----------------------------------------------------------------


class AgentThoughtPayload(BaseModel):
    agent: str  # AgentId: "author" | "medic" | "pilot"
    text: str


class AgentToolCallPayload(BaseModel):
    agent: str
    tool: str
    args: dict[str, Any]
    tool_call_id: str


class AgentToolResultPayload(BaseModel):
    agent: str
    tool: str
    tool_call_id: str
    ok: bool
    preview: str  # truncated ~500 chars for the feed; full results stay server-side


class AgentMessagePayload(BaseModel):
    """Streamed chat text. delta accumulates client-side; done=True closes the turn."""

    agent: str
    delta: str
    done: bool
    usage: dict[str, int] | None = None  # {input_tokens, output_tokens} on the final frame


# --- live values ---------------------------------------------------------------


class SensorReadingPayload(BaseModel):
    slug: str
    value: float
    unit: str = ""
    plausible: bool = True  # host verdict, never the model's opinion


class ActuatorStatePayload(BaseModel):
    slug: str
    level: float
    ok: bool


class HealthTrend(BaseModel):
    """Short-horizon degradation projection (see analytics/health.py)."""

    direction: str  # "stable" | "degrading" | "critical" | "insufficient_data"
    eta_s: float | None = None  # seconds to critical, only while worsening
    note: str | None = None


class SensorHealthPayload(BaseModel):
    """Derived health verdict for one driver — pushed on change + replayed on
    connect (like discovery presences). Computed from real accumulated readings
    only; "unknown"/"insufficient_data" are honest answers, never errors, and
    every non-healthy status ships a NAMED reason, never a bare score."""

    slug: str
    status: str  # "healthy" | "degrading" | "critical" | "unknown" | "not_monitored"
    reasons: list[str]
    readings_count: int
    baseline_target: int
    trend: HealthTrend


# --- discovery.* ---------------------------------------------------------------


class DeviceFoundPayload(BaseModel):
    """Plug-and-detect, the honest version.

    i2c + identity  -> confidence "exact" (address matched KNOWN_I2C_DEVICES)
    adc presence    -> confidence "unknown" ("something on GP27 — what is it?");
                       a raw voltage cannot reveal the part, the human names it.
    """

    bus: str  # "i2c" | "adc"
    addr: int | None = None  # i2c address, if bus == "i2c"
    pin: int | None = None  # GPIO, if bus == "adc"
    identity: str | None = None  # e.g. "SHTC3 temp/humidity" when known
    confidence: str = "unknown"  # "exact" | "unknown"
    suggested_spec: dict[str, Any] | None = None  # pre-filled BringupSpec fields


class DeviceLostPayload(BaseModel):
    bus: str
    addr: int | None = None
    pin: int | None = None


# --- driver.* ------------------------------------------------------------------


class DriverRegisteredPayload(BaseModel):
    slug: str
    display_name: str
    protocol_class: ProtocolClass
    pins: dict[str, int]
    tool_names: list[str]  # ["read_ldr"] / ["set_buzzer"] — the accreted capabilities
    code_hash: str
    unit: str = ""


class DriverUpdatedPayload(BaseModel):
    slug: str
    code_hash: str
    reason: str  # "repair" | "recommission"


# --- ui.* ----------------------------------------------------------------------


class UiPanelPayload(BaseModel):
    hint: str  # "focus" | "pulse"
    target: str  # PanelId: stepper|terminal|scope|rail|chat|board|feed


# --- command payloads (client -> server) ----------------------------------------


class CommissionCommand(BaseModel):
    """Either a one-click preset OR a full spec (fields map 1:1 to BringupSpec)."""

    preset_slug: str | None = None
    slug: str | None = None
    display_name: str | None = None
    protocol_class: ProtocolClass | None = None
    pins: dict[str, int] | None = None
    i2c_addr: int | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    unit: str = ""
    stimulus_hint: str = ""
    verify_with_slug: str | None = None
    extra_context: str = ""


class ReadCommand(BaseModel):
    slug: str


class SetCommand(BaseModel):
    slug: str
    level: float


class ChatCommand(BaseModel):
    text: str


class BoardScanCommand(BaseModel):
    pass


class StimulateCommand(BaseModel):
    """Mock-only: shift a simulated sensor's baseline (liveness demo offline).

    Rejected with system.error{code: "mock_only"} on a real board.
    """

    slug: str
    delta: float
