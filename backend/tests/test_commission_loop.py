"""THE spine test: fail -> repair -> pass in three attempts, zero hardware.

A scripted author (through the loop's injected seam — the exact seam the real
PydanticAI author and the mock author use) serves:

  attempt 1: while-loop code       -> the AST gate rejects, board never touched
  attempt 2: clean code            -> MockBoard answers a VERBATIM traceback
  attempt 3: clean code            -> MockBoard answers a plausible reading

Assertions pin the event narration order, the verbatim traceback event, the
attempt budget accounting, and the registry admission gate."""

from selfaware.bringup.loop import CommissionRunner
from selfaware.bringup.models import (
    BringupSpec,
    CommissionStatus,
    DriverGenOutput,
    ProtocolClass,
)
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.types import DriverStatus
from selfaware.hardware.mock_board import MockBoard, ScriptedExchange
from selfaware.hardware.session import BoardSession
from selfaware.registry.store import DriverRegistry

from tests.conftest import BusSpy

WHILE_LOOP_CODE = (
    "import machine\n"
    "class Driver:\n"
    "    def __init__(self):\n"
    "        self.adc = machine.ADC(27)\n"
    "    def read(self):\n"
    "        while True:\n"
    "            return self.adc.read_u16()\n"
)

GOOD_CODE = (
    "import machine\n"
    "class Driver:\n"
    "    def __init__(self):\n"
    "        self.adc = machine.ADC(27)\n"
    "    def read(self):\n"
    "        return self.adc.read_u16()\n"
)

BOARD_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "<stdin>", line 15, in <module>\n'
    '  File "<stdin>", line 11, in read\n'
    "AttributeError: 'ADC' object has no attribute 'read'\n"
)


def _spec() -> BringupSpec:
    return BringupSpec(
        slug="ldr",
        display_name="Light sensor (LDR)",
        protocol_class=ProtocolClass.ANALOG,
        pins={"adc": 27},
        expected_min=0,
        expected_max=65535,
        unit="raw",
    )


async def test_loop_converges_in_three(
    settings: Settings, bus: EventBus, bus_spy: BusSpy, mock_board: MockBoard
) -> None:
    seen: list[tuple[int, str | None]] = []

    async def scripted_author(spec: BringupSpec, attempt: int, last_error: str | None) -> DriverGenOutput:
        seen.append((attempt, last_error))
        code = WHILE_LOOP_CODE if attempt == 1 else GOOD_CODE
        return DriverGenOutput(
            reasoning=f"attempt {attempt}", driver_code=code, imports_used="machine"
        )

    # attempt 1 never reaches the board (gate rejects the while loop);
    # attempt 2 gets the traceback, attempt 3 the plausible reading.
    mock_board.queue(
        ScriptedExchange(stdout="", stderr=BOARD_TRACEBACK),
        ScriptedExchange(stdout="41250\n"),
    )
    await mock_board.connect()

    session = BoardSession(mock_board, bus, settings)
    registry = DriverRegistry(bus)
    runner = CommissionRunner(session, registry, bus, scripted_author, settings)

    result = await runner.run(_spec(), "c-1")

    # -- outcome ---------------------------------------------------------------
    assert result.status is CommissionStatus.PASSED
    assert len(result.attempts) == 3
    assert result.attempts[-1].passed
    assert result.final_reading == 41250.0

    # -- the seam saw the right repair context ----------------------------------
    assert seen[0] == (1, None)
    assert seen[1][0] == 2 and "static gate rejected" in (seen[1][1] or "")
    assert seen[2][0] == 3 and seen[2][1] == BOARD_TRACEBACK  # VERBATIM, whole

    # -- event narration ---------------------------------------------------------
    bus_spy.drain()
    commission_events = [e for e in bus_spy.events if e.type.startswith("commission.")]
    assert commission_events[0].type == "commission.started"
    assert commission_events[-1].type == "commission.passed"
    assert commission_events[-1].payload["attempts_used"] == 3

    tracebacks = [e for e in bus_spy.events if e.type == "commission.traceback"]
    assert len(tracebacks) == 1
    assert tracebacks[0].payload["traceback"] == BOARD_TRACEBACK  # never trimmed
    assert tracebacks[0].payload["attempt"] == 2

    stages = [
        (e.payload["attempt"], e.payload["stage"], e.payload["status"])
        for e in bus_spy.events
        if e.type == "commission.stage"
    ]
    # attempt 1: generate ok, validate fails, board untouched
    assert (1, "generate", "passed") in stages
    assert (1, "validate", "failed") in stages
    assert (1, "deploy", "started") not in stages
    # attempts 2+3 repair (verbatim error in hand), attempt 3 tests green
    assert (2, "repair", "started") in stages
    assert (3, "repair", "started") in stages
    assert (3, "test", "passed") in stages

    # -- admission gate: registered exactly because it passed on (mock) silicon ---
    record = registry.get("ldr")
    assert record is not None
    assert record.status is DriverStatus.ACTIVE
    assert record.driver_code == GOOD_CODE
    assert record.attempts_used == 3
    registered = [e for e in bus_spy.events if e.type == "driver.registered"]
    assert len(registered) == 1


async def test_budget_exhaustion_is_an_honest_failure(
    settings: Settings, bus: EventBus, bus_spy: BusSpy, mock_board: MockBoard
) -> None:
    async def hopeless_author(spec: BringupSpec, attempt: int, last_error: str | None) -> DriverGenOutput:
        return DriverGenOutput(reasoning="stuck", driver_code=WHILE_LOOP_CODE, imports_used="machine")

    await mock_board.connect()
    session = BoardSession(mock_board, bus, settings)
    registry = DriverRegistry(bus)
    runner = CommissionRunner(session, registry, bus, hopeless_author, settings)

    result = await runner.run(_spec(), "c-2")

    assert result.status is CommissionStatus.FAILED
    assert len(result.attempts) == settings.max_attempts
    assert registry.get("ldr") is None  # no pass, no registration — ever
    failed = bus_spy.of_type("commission.failed")
    assert len(failed) == 1
    assert failed[0].payload["attempts_used"] == settings.max_attempts
    assert mock_board.soft_reset_count >= 1  # clean line after the honest FAILED
