"""Domain models for the self-repair loop — the single home agents/ imports from.

The wire-vocabulary enums (ProtocolClass, CommissionStage, StageStatus) are
OWNED by the event contract (`selfaware.events.types`) because their values
appear inside payloads; this module RE-EXPORTS them so the rest of the domain
layer has exactly one import point and never reaches into events/ directly.

`DriverGenOutput` is the only thing the LLM ever produces. It is DELIBERATELY
FLAT — no nesting, no Optional/Union — because nested JSON schema
($defs/$ref/anyOf) silently degrades on smaller models and gateways. Field
ORDER is load-bearing: structured output is emitted top-to-bottom, so
`reasoning` comes first and the model thinks before it codes.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from selfaware.events.types import CommissionStage, ProtocolClass, StageStatus

__all__ = [
    "AttemptRecord",
    "BringupSpec",
    "CommissionResult",
    "CommissionStage",
    "CommissionStatus",
    "DriverGenOutput",
    "ProtocolClass",
    "StageStatus",
]


class BringupSpec(BaseModel):
    """Everything the host knows before the loop starts.

    Rendered as text into the author prompt — the protocol class is named
    EXPLICITLY so the model never guesses the read mechanism (voltage vs bus
    vs pulse timing vs actuation).
    """

    slug: str  # 'ldr', 'ultrasonic' — becomes the read_<slug>/set_<slug> tool name
    display_name: str
    protocol_class: ProtocolClass
    pins: dict[str, int]  # role -> GPIO: {'adc': 27} | {'trig': 14, 'echo': 15} | {'sda': 4, 'scl': 5}
    i2c_addr: int | None = None  # e.g. 0x70 for SHTC3
    expected_min: float | None = None  # host-side plausibility window
    expected_max: float | None = None
    unit: str = ""
    stimulus_hint: str = ""  # 'cover the sensor with your hand' — drives the liveness UX
    verify_with_slug: str | None = None  # OUTPUT class only: already-commissioned cross-modal verifier
    extra_context: str = ""  # freeform prompt notes (board-revision quirks, UNCONFIRMED pins)


class DriverGenOutput(BaseModel):
    """LLM structured output — flat, ordered, and NOTHING else.

    There is deliberately no `read_call` field: the HOST authors the harness
    call (`bringup/harness.py`), so the model can never smuggle behavior into
    the test stage.
    """

    reasoning: str = Field(
        description=(
            "Brief approach BEFORE the code. On attempt >= 2: what the previous "
            "verbatim error implies and what you changed."
        )
    )
    driver_code: str = Field(
        description=(
            "MicroPython source defining `class Driver` with read() -> number "
            "(sensors) or set(level) -> None, non-blocking (outputs). No while "
            "loops, no filesystem, no IRQs — the static gate rejects them."
        )
    )
    imports_used: str = Field(
        description=(
            "Comma-separated top-level modules the code imports, e.g. "
            "'machine, time'. The gate cross-checks this against the AST "
            "(lie detector)."
        )
    )


class AttemptRecord(BaseModel):
    """One turn of the ratchet, kept for the honest post-mortem."""

    attempt: int
    stage_reached: CommissionStage
    gate_reason: str | None = None  # why the AST gate rejected, if it did
    traceback: str | None = None  # VERBATIM board stderr, if any
    reading: float | None = None
    passed: bool = False


class CommissionStatus(StrEnum):
    """Terminal outcome of one commission run (domain-only, not a wire enum)."""

    PASSED = "passed"
    FAILED = "failed"


class CommissionResult(BaseModel):
    """Honest outcome. FAILED carries the last verbatim traceback and every
    attempt — no silent success, no infinite retry."""

    spec: BringupSpec
    status: CommissionStatus
    attempts: list[AttemptRecord]
    final_code: str | None = None
    final_reading: float | None = None
    failure_reason: str | None = None
