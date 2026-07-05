"""OledNarrator — the board narrates its own agentic work.

Three concerns: (1) the pure line derivation matches theater/agents.ts::derivePhase,
(2) NarratorModel reduces the same bus events the console reads, (3) end-to-end
against MockBoard the render payloads are valid MicroPython that lands on the
wire and never errors (so `make demo-mock` stays green with no display).
"""

from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.types import EventType
from selfaware.hardware.mock_board import MockBoard
from selfaware.hardware.oled_narrator import (
    NarratorModel,
    OledNarrator,
    agent_lines,
    message_lines,
    telemetry_lines,
)
from selfaware.hardware.oled_render import build_init_payload, draw_payload
from selfaware.hardware.session import BoardSession


def _joined(lines: list[str]) -> str:
    return "\n".join(lines)


# --- pure derivation: parity with derivePhase --------------------------------


def test_agent_lines_no_board() -> None:
    lines, invert = agent_lines(connected=False, driver_count=0)
    assert invert
    assert lines[0] == "SELFAWARE"
    assert "NO BOARD" in _joined(lines)


def test_agent_lines_idle_awaiting_vs_live() -> None:
    awaiting, _ = agent_lines(connected=True, driver_count=0)
    assert "AWAITING" in _joined(awaiting)

    live, _ = agent_lines(connected=True, driver_count=2)
    body = _joined(live)
    assert "LIVE" in body and "NOMINAL" in body
    assert "2 live tools" in body


def test_agent_lines_map_every_stage_to_its_banner() -> None:
    # (stage, status, outcome) -> expected banner + a headline fragment
    cases = [
        (("generate", "started", None), "AUTHOR", "WRITING"),
        (("repair", "started", None), "MEDIC", "READING"),
        (("validate", "failed", None), "HOST", "REJECTED"),
        (("validate", "started", None), "HOST", "REVIEW"),
        (("deploy", "started", None), "BOARD", "LOADING"),
        (("test", None, None), "BOARD", "RUNNING"),
        (("test", "failed", None), "BOARD", "TRACEBACK"),
        (("test", "passed", None), "HOST", "VERIFYING"),
        ((None, None, "passed"), "PILOT", "SIGNAL ACQUIRED"),
        ((None, None, "failed"), "BOARD", "NOT ADMITTED"),
    ]
    for (stage, status, outcome), banner, fragment in cases:
        lines, invert = agent_lines(
            connected=True,
            driver_count=0,
            active=True,
            slug="ldr",
            display_name="Light sensor",
            attempt=2,
            max_attempts=4,
            stage=stage,
            status=status,
            outcome=outcome,
        )
        assert invert
        assert lines[0] == banner, f"{stage}/{status}/{outcome} -> {lines[0]!r} != {banner!r}"
        # words may land on different rows (16-col word-wrap) — assert each appears
        body = _joined(lines)
        assert all(w in body for w in fragment.split()), f"{fragment!r} missing from {lines!r}"


def test_agent_lines_show_attempt_while_running_not_at_terminal() -> None:
    running, _ = agent_lines(
        connected=True, driver_count=0, active=True, slug="ldr", display_name="Light",
        attempt=2, max_attempts=4, stage="repair", status="started",
    )
    assert "attempt 2/4" in _joined(running)

    passed, _ = agent_lines(
        connected=True, driver_count=1, active=True, slug="ldr", display_name="Light",
        attempt=2, max_attempts=4, stage=None, status=None, outcome="passed",
    )
    assert "attempt" not in _joined(passed)


def test_telemetry_lines_readings_and_health_chip() -> None:
    lines, invert = telemetry_lines(
        connected=True,
        mock=True,
        readings={"ldr": (41250.0, "raw"), "shtc3": (22.5, "degC")},
        health={"ldr": "healthy", "shtc3": "critical"},
    )
    assert invert
    body = _joined(lines)
    assert "BOARD mock" in body
    assert "LDR" in body and "41250raw" in body and "+" in body  # healthy chip
    assert "22.5degC" in body and "!" in body  # critical chip


def test_telemetry_lines_no_sensors() -> None:
    lines, _ = telemetry_lines(connected=True, mock=False, readings={}, health={})
    assert "no live sensors" in _joined(lines)


# --- render payloads are valid MicroPython -----------------------------------


def test_init_payload_compiles() -> None:
    compile(build_init_payload(4, 5, 0x3C), "<init>", "exec")


def test_draw_payload_compiles_clips_and_escapes() -> None:
    # 40-char line clips to 16; embedded quote must not break the exec string.
    payload = draw_payload(["AUTHOR", "x" * 40, "it's fine"], invert_header=True)
    compile(payload, "<draw>", "exec")
    assert "'" + "x" * 16 + "'" in payload  # clipped to 16 cols
    assert "x" * 17 not in payload
    assert payload.endswith("_oled.show()")


# --- NarratorModel reduces the same events the console reads ------------------


def test_model_reduces_commission_and_readings() -> None:
    m = NarratorModel()
    m.apply(EventType.BOARD_STATUS, {"connected": True, "busy": False, "mock": True})
    assert m.connected and m.mock

    m.apply(EventType.COMMISSION_STARTED, {"slug": "ldr", "display_name": "Light", "max_attempts": 4})
    assert m.active and m.slug == "ldr" and m.max_attempts == 4

    m.apply(EventType.COMMISSION_STAGE, {"attempt": 2, "stage": "repair", "status": "started"})
    assert m.stage == "repair" and m.attempt == 2

    m.apply(EventType.SENSOR_READING, {"slug": "ldr", "value": 41250, "unit": "raw"})
    assert m.readings["ldr"] == (41250.0, "raw")

    m.apply(EventType.SENSOR_HEALTH, {"slug": "ldr", "status": "healthy"})
    assert m.health["ldr"] == "healthy"

    m.apply(EventType.COMMISSION_PASSED, {"slug": "ldr", "reading": 40000, "unit": "raw"})
    assert m.outcome == "passed"

    m.apply(EventType.DRIVER_REGISTERED, {"slug": "ldr"})
    assert m.driver_count == 1


# --- end to end against MockBoard --------------------------------------------


async def test_render_lands_valid_payloads_and_never_errors() -> None:
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)
    board = MockBoard()
    await board.connect()
    session = BoardSession(board, bus, settings)
    narrator = OledNarrator(session, bus, settings)
    narrator._model.connected = True  # noqa: SLF001 — drive the render without the bus task

    await narrator._maybe_render()  # noqa: SLF001

    joined = "\n".join(board.exec_log)
    assert "framebuf" in joined  # the init payload went out first
    assert "_oled.show()" in joined  # a frame was drawn
    assert not narrator._absent  # mock returns clean -> the display is "present"  # noqa: SLF001
    assert narrator._initialized  # noqa: SLF001


async def test_draw_commission_animates_through_a_board_handle() -> None:
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)
    board = MockBoard()
    await board.connect()
    session = BoardSession(board, bus, settings)
    narrator = OledNarrator(session, bus, settings)

    # The commission loop passes its ExclusiveBoard; MockBoard satisfies the same
    # exec() protocol, so we hand it directly (race-free, explicit stage).
    await narrator.draw_commission(
        board,
        slug="ldr",
        display_name="Light sensor",
        attempt=2,
        max_attempts=4,
        stage="repair",
        status="started",
    )
    joined = "\n".join(board.exec_log)
    assert "MEDIC" in joined  # the medic banner reached the wire
    assert not narrator._absent  # noqa: SLF001


async def test_absent_display_backs_off_and_does_not_spam() -> None:
    """An OLED that raises on init (not on the bus) must be marked absent and
    left alone — never re-tried every tick (that would flood the wire)."""
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)

    class _NoDisplayBoard(MockBoard):
        async def exec(self, code: str, timeout_s: float):  # type: ignore[override]
            res = await super().exec(code, timeout_s)
            # Simulate the SSD1306 not answering: init raises OSError like a real
            # absent I2C device would.
            if "framebuf" in code:
                from selfaware.hardware.base import ExecResult

                return ExecResult(stdout="", stderr="OSError: [Errno 19] ENODEV", duration_s=0.0)
            return res

    board = _NoDisplayBoard()
    await board.connect()
    session = BoardSession(board, bus, settings)
    narrator = OledNarrator(session, bus, settings)
    narrator._model.connected = True  # noqa: SLF001

    await narrator._maybe_render()  # noqa: SLF001
    assert narrator._absent  # noqa: SLF001
    execs_after_first = len(board.exec_log)

    await narrator._maybe_render()  # noqa: SLF001 — should be a no-op during backoff
    assert len(board.exec_log) == execs_after_first  # no new wire traffic


# --- the external message view (MCP display_message) ---------------------------


def test_message_lines_wrap_and_name_the_speaker() -> None:
    lines, invert = message_lines("HELLO FROM CLAUDE this wraps across rows")
    assert lines[0] == "AGENT SAYS"  # the banner names the speaker
    assert invert is True
    assert any("HELLO" in line for line in lines[1:])


async def test_say_shows_then_expires_back_to_rotation() -> None:
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)
    board = MockBoard()
    await board.connect()
    session = BoardSession(board, bus, settings)
    narrator = OledNarrator(session, bus, settings)
    narrator._consumer = object()  # noqa: SLF001 — satisfy say()'s started check without the bus task

    assert narrator.say("HELLO FROM CLAUDE", hold_s=60.0) is True
    assert narrator._current_view() == "message"  # noqa: SLF001
    narrator._model.connected = True  # noqa: SLF001
    await narrator._maybe_render()  # noqa: SLF001
    joined = "\n".join(board.exec_log)  # 16-col wrap may split the words across rows
    assert "HELLO" in joined and "CLAUDE" in joined  # reached the wire
    assert "AGENT SAYS" in joined

    narrator._message_until = 0.0  # noqa: SLF001 — force expiry
    assert narrator._current_view() in ("agent", "telemetry")  # noqa: SLF001
    assert narrator._message is None  # noqa: SLF001 — cleared, not lingering


async def test_say_never_preempts_an_active_commission() -> None:
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)
    board = MockBoard()
    await board.connect()
    narrator = OledNarrator(BoardSession(board, bus, settings), bus, settings)
    narrator._consumer = object()  # noqa: SLF001
    narrator._model.active = True  # noqa: SLF001 — a commission owns the screen

    assert narrator.say("interruption attempt", hold_s=60.0) is True
    assert narrator._current_view() == "agent"  # noqa: SLF001 — the commission wins


async def test_say_refuses_honestly_when_absent_or_not_started() -> None:
    bus = EventBus()
    settings = Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)
    board = MockBoard()
    await board.connect()
    narrator = OledNarrator(BoardSession(board, bus, settings), bus, settings)

    assert narrator.say("hi") is False  # not started — no consumer task

    narrator._consumer = object()  # noqa: SLF001
    narrator._absent = True  # noqa: SLF001 — display proved missing
    assert narrator.say("hi") is False
