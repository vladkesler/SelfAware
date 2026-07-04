"""MockBoard — the demo-without-hardware engine. FULLY WORKING today.

Two modes, composable, checked in this order per exec:

  1. Scripted: a queue of ScriptedExchange consumed per exec — this is how the
     fail -> repair -> pass demo runs offline (attempt 1 returns a genuine-
     looking board traceback, attempt 2 a plausible reading).
  2. Simulated sensors: when no script entry claims the exec, regexes over the
     exec'd CODE select a value generator (sine + noise per slug), so
     sensor.reading streams look alive and `stimulate(slug, delta)` can nudge
     a baseline for the liveness beat.

Never a silent fallback: MockBoard is only ever constructed when
SELFAWARE_MOCK_BOARD=true, and its port_id ('mock://demo') / is_mock flag are
badged in the UI.
"""

import asyncio
import math
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field

from pydantic import BaseModel

from selfaware.hardware.base import ExecResult

MOCK_PORT_ID = "mock://demo"


class ScriptedExchange(BaseModel):
    """One canned reply.

    match=None  -> consumed strictly next-in-order (a script).
    match=regex -> consumed only when the regex matches the exec'd code;
                   a non-matching exec falls through to the simulators.
    delay_s defaults to 0 so unit tests are instant; demo scripts set
    theatrical latency explicitly so the UI animates believably.
    """

    match: str | None = None
    stdout: str = ""
    stderr: str = ""  # a realistic VERBATIM MicroPython traceback for repair demos
    delay_s: float = 0.0


@dataclass
class SimulatedSensor:
    """A live-looking value stream: base + slow sine + noise + stimulate offset."""

    slug: str
    pattern: re.Pattern[str]
    base: float
    amplitude: float = 2000.0
    period_s: float = 7.0
    noise: float = 150.0
    offset: float = 0.0  # shifted by stimulate()
    _t0: float = field(default_factory=time.monotonic)

    def value(self) -> float:
        t = time.monotonic() - self._t0
        wave = self.amplitude * math.sin(2 * math.pi * t / self.period_s)
        return self.base + wave + random.gauss(0.0, self.noise) + self.offset


class MockBoard:
    """Implements BoardTransport with zero hardware. See module docstring."""

    def __init__(self, script: list[ScriptedExchange] | None = None) -> None:
        self.port_id = MOCK_PORT_ID
        self.is_mock = True
        self._connected = False
        self._script: deque[ScriptedExchange] = deque(script or [])
        self._sims: list[SimulatedSensor] = _default_simulators()
        self.exec_log: list[str] = []  # every exec'd payload, for tests/inspection
        self.soft_reset_count = 0

    # --- BoardTransport --------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def exec(self, code: str, timeout_s: float) -> ExecResult:
        """Scripted head first, then simulators, then a silent success.

        Honors the host-timeout contract for real: an exchange whose delay_s
        exceeds timeout_s returns ExecResult(timed_out=True) after timeout_s —
        so the session's timeout -> soft_reset policy is testable offline.
        """
        started = time.monotonic()
        self.exec_log.append(code)

        exchange = self._claim_scripted(code)
        if exchange is not None:
            if exchange.delay_s > timeout_s:
                await asyncio.sleep(timeout_s)
                return ExecResult(stdout="", stderr="", duration_s=time.monotonic() - started, timed_out=True)
            if exchange.delay_s > 0:
                await asyncio.sleep(exchange.delay_s)
            return ExecResult(
                stdout=exchange.stdout,
                stderr=exchange.stderr,
                duration_s=time.monotonic() - started,
            )

        for sim in self._sims:
            if sim.pattern.search(code):
                value = sim.value()
                return ExecResult(
                    stdout=f"{value:.1f}\n",
                    stderr="",
                    duration_s=time.monotonic() - started,
                )

        return ExecResult(stdout="", stderr="", duration_s=time.monotonic() - started)

    async def soft_reset(self) -> None:
        """Clean line: drop any remaining scripted exchanges (cursor reset)."""
        self.soft_reset_count += 1
        self._script.clear()

    async def close(self) -> None:
        self._connected = False

    # --- mock-only controls ------------------------------------------------------

    def queue(self, *exchanges: ScriptedExchange) -> None:
        """Append canned replies (consumed before any simulator can answer)."""
        self._script.extend(exchanges)

    def stimulate(self, slug: str, delta: float) -> None:
        """Shift a simulated sensor's baseline — the offline liveness stimulus.

        Wired to cmd.stimulate (mock-only; rejected on a real board).
        Raises KeyError for an unknown slug so typos fail loudly.
        """
        for sim in self._sims:
            if sim.slug == slug:
                sim.offset += delta
                return
        raise KeyError(f"no simulated sensor for slug {slug!r}")

    def _claim_scripted(self, code: str) -> ScriptedExchange | None:
        """Consume the head of the script if it claims this exec.

        match=None claims unconditionally (strict order); a regex head claims
        only a matching exec — otherwise the script stays put and the
        simulators get their turn.
        """
        if not self._script:
            return None
        head = self._script[0]
        if head.match is None or re.search(head.match, code):
            return self._script.popleft()
        return None


def _default_simulators() -> list[SimulatedSensor]:
    """Generators keyed by regex over exec'd driver code.

    Patterns target what generated MicroPython actually contains: 'ADC(27)'
    for the LDR, 'ADC(26)' for the pot, the SHTC3 address for the temp brick.
    """
    return [
        SimulatedSensor(slug="ldr", pattern=re.compile(r"ADC\(\s*27\s*\)"), base=30000.0),
        SimulatedSensor(slug="pot", pattern=re.compile(r"ADC\(\s*26\s*\)"), base=45000.0),
        SimulatedSensor(
            slug="shtc3",
            pattern=re.compile(r"0x70|(?<!\d)112(?!\d)"),
            base=22.5,
            amplitude=1.5,
            noise=0.1,
        ),
    ]


def demo_fail_then_pass_script(slug: str = "ldr") -> list[ScriptedExchange]:
    """The rehearsable demo arc: gate-passing code, board-raised failure, recovery.

    Attempt 1: the exec'd driver passed the static gate, but the *board*
    raises — the exact AttributeError a real RP2040 gives when code calls
    ESP32's adc.read() (the mock author's scripted habit; `read` is a legal
    attribute name, so no static gate can catch it). Verbatim: the un-fakeable
    signal the repair prompt embeds untouched. Attempt 2: a plausible,
    non-railed reading, so plausibility passes and the driver registers.

    Theatrical delay_s so the UI stepper animates believably.
    """
    return [
        ScriptedExchange(
            match=None,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                '  File "<stdin>", line 15, in <module>\n'
                '  File "<stdin>", line 11, in read\n'
                "AttributeError: 'ADC' object has no attribute 'read'\n"
            ),
            delay_s=0.15,
        ),
        ScriptedExchange(
            match=None,
            stdout="41250\n",
            delay_s=0.15,
        ),
    ]
