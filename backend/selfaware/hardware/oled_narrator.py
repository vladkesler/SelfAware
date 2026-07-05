"""OledNarrator — the board narrates its own agentic work on the SSD1306.

Shape mirrors analytics/watcher.py::HealthWatcher: a background task fed by a
bus.subscribe() subscription, failure-isolated, started/stopped from the api
lifespan. It owns NO new data — every fact comes off the same EventBus the web
console reads, and the headline strings are ported verbatim from
frontend/src/theater/agents.ts::derivePhase() so the OLED and the console can
never disagree.

Wire discipline:
  * At rest it draws through session.exec() (THE shared lock) — poller-safe.
  * A commission holds session.exclusive() end-to-end, so at-rest draws are
    skipped while board.busy; the commission loop instead calls draw_commission()
    with its own ExclusiveBoard handle, animating the arc live.
  * Frames are coalesced: a draw only hits the wire when the rendered payload
    actually changed (this also drives the at-rest agent<->telemetry rotation
    without a redraw storm).
  * `_oled` lives as a board global; a soft_reset (the loop's recovery) wipes
    it, and the board's own NameError is the re-init trigger.

The line-derivation is pure module functions (agent_lines / telemetry_lines) so
tests assert derivePhase parity without a board.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Protocol

from selfaware.config import Settings
from selfaware.events.bus import EventBus, Subscription
from selfaware.events.types import EventType
from selfaware.hardware.oled_render import (
    MAX_COLS,
    build_init_payload,
    draw_payload,
    is_uninitialized_error,
)
from selfaware.hardware.base import ExecResult

_HEALTH_CHIP = {"healthy": "+", "degrading": "~", "critical": "!", "unknown": "?", "not_monitored": ""}


class _Execer(Protocol):
    """BoardSession and ExclusiveBoard both satisfy this — the only method the
    narrator needs on the wire. Keeps draw_commission() handle-agnostic."""

    async def exec(self, code: str, timeout_s: float | None = None) -> ExecResult: ...


# --- pure line derivation (ported from theater/agents.ts::derivePhase) --------


def _ascii_words(text: str) -> list[str]:
    return text.split()


def _wrap(text: str, max_lines: int, width: int = MAX_COLS) -> list[str]:
    """Greedy word-wrap to `width` cols, at most `max_lines` rows."""
    lines: list[str] = []
    cur = ""
    for word in _ascii_words(text):
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                return lines[:max_lines]
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines[:max_lines]


def _commission_phase(
    slug: str,
    display_name: str,
    stage: str | None,
    status: str | None,
    outcome: str | None,
    fail_reason: str | None,
) -> tuple[str, str, str]:
    """(banner, headline, sub) — the one-glance truth, verbatim from derivePhase."""
    name = display_name or slug
    if outcome == "passed":
        return ("PILOT", "LIVE // SIGNAL ACQUIRED", f"{name} admitted - read_{slug} is a live tool")
    if outcome == "failed":
        return ("BOARD", "NOT ADMITTED", fail_reason or "the board never vouched for it")
    if stage == "generate":
        return ("AUTHOR", "AUTHOR // WRITING THE DRIVER", f"composing a driver for {name}...")
    if stage == "repair":
        return ("MEDIC", "MEDIC // READING THE ERROR", "feeding the board's verbatim traceback back in...")
    if stage == "validate":
        if status == "failed":
            return ("HOST", "REJECTED // THE GATE CAUGHT IT", "the static safety gate refused the code")
        return ("HOST", "AUTHOR // CODE UNDER REVIEW", "the host gate vets the code before a pin...")
    if stage == "deploy":
        return ("BOARD", "THE BOARD // LOADING THE DRIVER", "loading over the raw REPL...")
    if stage == "test":
        if status == "failed":
            return ("BOARD", "TRACEBACK // BOARD REJECTED IT", "the chip raised a verbatim error")
        if status == "passed":
            return ("HOST", "HOST // VERIFYING THE READING", "checking the value is physically plausible...")
        return ("BOARD", "THE BOARD // RUNNING IT", "the real board runs the driver - the arbiter")
    return ("AUTHOR", f"COMMISSIONING {name.upper()}", "bringing a dead part to life...")


def agent_lines(
    *,
    connected: bool,
    driver_count: int,
    active: bool = False,
    slug: str = "",
    display_name: str = "",
    attempt: int = 0,
    max_attempts: int = 0,
    stage: str | None = None,
    status: str | None = None,
    outcome: str | None = None,
    fail_reason: str | None = None,
) -> tuple[list[str], bool]:
    """The agent/commission card. Returns (lines, invert_header=True).

    Row 0 is the inverted banner (active agent, or SELFAWARE at rest); up to six
    body rows follow.
    """
    if not connected:
        return (["SELFAWARE", "NO BOARD", "connect the pico", "over USB and the", "host takes over"], True)

    if not active:
        if driver_count > 0:
            body = _wrap("LIVE // SYSTEMS NOMINAL", 2)
            plural = "" if driver_count == 1 else "s"
            body.append(f"{driver_count} live tool{plural}")
            body += _wrap("ask the pilot to read a sensor", 2)
            return (["SELFAWARE", *body[:6]], True)
        body = _wrap("AWAITING HARDWARE", 2)
        body += _wrap("plug a part in - the host scans the bus", 3)
        return (["SELFAWARE", *body[:6]], True)

    banner, headline, sub = _commission_phase(slug, display_name, stage, status, outcome, fail_reason)
    body = _wrap(headline, 2)
    if outcome is None and stage is not None:
        # The stage is already in the headline; keep this line short + readable.
        body.append(f"attempt {attempt}/{max_attempts}"[:MAX_COLS])
    body += _wrap(sub, 2)
    return ([banner, *body[:6]], True)


def message_lines(text: str) -> tuple[list[str], bool]:
    """The agent-message card: an external caller (the MCP display_message
    tool) speaking on the physical display. Same wrap discipline as every
    other card; the banner names the speaker so a viewer never mistakes it
    for the board's own narration."""
    body = _wrap(text, 6)
    if not body:
        body = ["(empty message)"]
    return (["AGENT SAYS", *body], True)


def _fmt_value(v: float) -> str:
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.1f}"


def telemetry_lines(
    *,
    connected: bool,
    mock: bool,
    readings: dict[str, tuple[float, str]],
    health: dict[str, str],
) -> tuple[list[str], bool]:
    """The at-rest telemetry card: board line + per-sensor value & health chip."""
    board = "BOARD " + ("mock" if mock else ("online" if connected else "offline"))
    lines = ["TELEMETRY", board]
    if readings:
        for slug, (value, unit) in list(readings.items())[:5]:
            chip = _HEALTH_CHIP.get(health.get(slug, ""), "")
            row = f"{slug[:5].upper():<5} {_fmt_value(value)}{unit}"
            if chip:
                row = f"{row} {chip}"
            lines.append(row[:MAX_COLS])
    else:
        lines.append("no live sensors")
        lines.append("commission a part")
    return (lines[:7], True)


# --- the model + the task -----------------------------------------------------


@dataclass
class NarratorModel:
    """In-memory mirror of the bus, just enough to render. Mutated by the bus
    consumer only; never touches the wire."""

    connected: bool = False
    busy: bool = False
    mock: bool = False
    drivers: set[str] = field(default_factory=set)
    # active commission (None outside a run)
    active: bool = False
    slug: str = ""
    display_name: str = ""
    attempt: int = 0
    max_attempts: int = 0
    stage: str | None = None
    status: str | None = None
    outcome: str | None = None
    fail_reason: str | None = None
    terminal_at: float = 0.0
    readings: dict[str, tuple[float, str]] = field(default_factory=dict)
    health: dict[str, str] = field(default_factory=dict)

    @property
    def driver_count(self) -> int:
        return len(self.drivers)

    def apply(self, etype: str, p: dict) -> None:
        if etype == EventType.BOARD_STATUS:
            self.connected = bool(p.get("connected", self.connected))
            self.busy = bool(p.get("busy", False))
            self.mock = bool(p.get("mock", self.mock))
        elif etype == EventType.BOARD_CONNECTED:
            self.connected = True
            self.mock = bool(p.get("mock", self.mock))
        elif etype == EventType.BOARD_DISCONNECTED:
            self.connected = False
        elif etype == EventType.COMMISSION_STARTED:
            self.active = True
            self.slug = p.get("slug", "")
            self.display_name = p.get("display_name", "")
            self.max_attempts = int(p.get("max_attempts", 0))
            self.attempt = 1
            self.stage = None
            self.status = None
            self.outcome = None
            self.fail_reason = None
        elif etype == EventType.COMMISSION_STAGE:
            self.active = True
            self.attempt = int(p.get("attempt", self.attempt))
            self.stage = p.get("stage", self.stage)
            self.status = p.get("status", self.status)
        elif etype == EventType.COMMISSION_PASSED:
            self.active = True
            self.outcome = "passed"
            self.terminal_at = time.monotonic()
            r = p.get("reading")
            if r is not None:
                self.readings[p.get("slug", self.slug)] = (float(r), p.get("unit", ""))
        elif etype == EventType.COMMISSION_FAILED:
            self.active = True
            self.outcome = "failed"
            self.fail_reason = p.get("reason", "")
            self.terminal_at = time.monotonic()
        elif etype == EventType.DRIVER_REGISTERED:
            self.drivers.add(p.get("slug", ""))
        elif etype == EventType.SENSOR_READING:
            self.readings[p.get("slug", "")] = (float(p.get("value", 0.0)), p.get("unit", ""))
        elif etype == EventType.SENSOR_HEALTH:
            self.health[p.get("slug", "")] = p.get("status", "unknown")


class OledNarrator:
    """Bus-fed SSD1306 narrator. start()/stop() like the other watchers."""

    def __init__(self, session, bus: EventBus, settings: Settings) -> None:
        self._session = session
        self._bus = bus
        self._settings = settings
        self._model = NarratorModel()
        self._sub: Subscription | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._renderer: asyncio.Task[None] | None = None
        # render bookkeeping
        self._initialized = False
        self._last_payload: str | None = None
        self._view = "agent"  # at-rest rotation cursor
        self._rotate_at = 0.0
        # absent-OLED backoff (don't hammer a bus with no display)
        self._absent = False
        self._retry_at = 0.0
        # external message override (MCP display_message) — text + expiry
        self._message: str | None = None
        self._message_until = 0.0

    # --- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        if not self._settings.oled_enabled or self._consumer is not None:
            return
        self._sub = self._bus.subscribe()
        self._consumer = asyncio.create_task(self._consume_loop(), name="selfaware-oled-consume")
        self._renderer = asyncio.create_task(self._render_loop(), name="selfaware-oled-render")

    async def stop(self) -> None:
        for task in (self._renderer, self._consumer):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._renderer = self._consumer = None
        if self._sub is not None:
            self._bus.unsubscribe(self._sub)
            self._sub = None

    # --- bus consumer (no wire I/O) ------------------------------------------

    async def _consume_loop(self) -> None:
        assert self._sub is not None
        async for event in self._sub:
            try:
                self._model.apply(event.type, event.payload)
            except Exception:  # noqa: BLE001 — a malformed payload must not kill the narrator
                pass

    # --- render loop (at rest) -----------------------------------------------

    async def _render_loop(self) -> None:
        while True:
            try:
                await self._maybe_render()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — the OLED is ambience, never a health check
                pass
            await asyncio.sleep(self._settings.oled_refresh_s)

    def say(self, text: str, hold_s: float = 8.0) -> bool:
        """Queue an external message for the display (the MCP display_message
        tool). Returns False — honestly — when the narrator is disabled or the
        OLED has proven absent; True means the render loop will show it, though
        an active commission keeps owning the screen until it finishes."""
        if not self._settings.oled_enabled or self._consumer is None or self._absent:
            return False
        self._message = text
        self._message_until = time.monotonic() + hold_s
        self._last_payload = None  # force a draw even if the frame matches
        return True

    def _current_view(self) -> str:
        """Force the agent card during (and briefly after) a commission; then
        an external message if one is live; else rotate agent<->telemetry on
        the slow cadence."""
        m = self._model
        now = time.monotonic()
        if m.active:
            if m.outcome is None:
                return "agent"
            if now - m.terminal_at < self._settings.oled_rotate_s * 1.5:
                return "agent"
            m.active = False  # terminal frame shown long enough; resume idle
        if self._message is not None:
            if now < self._message_until:
                return "message"
            self._message = None  # expired; resume the idle rotation
        if now - self._rotate_at >= self._settings.oled_rotate_s:
            self._rotate_at = now
            self._view = "telemetry" if self._view == "agent" else "agent"
        return self._view

    def _frame(self, view: str) -> str:
        m = self._model
        if view == "message":
            lines, invert = message_lines(self._message or "")
        elif view == "telemetry":
            lines, invert = telemetry_lines(
                connected=m.connected, mock=m.mock, readings=m.readings, health=m.health
            )
        else:
            lines, invert = agent_lines(
                connected=m.connected,
                driver_count=m.driver_count,
                active=m.active,
                slug=m.slug,
                display_name=m.display_name,
                attempt=m.attempt,
                max_attempts=m.max_attempts,
                stage=m.stage,
                status=m.status,
                outcome=m.outcome,
                fail_reason=m.fail_reason,
            )
        return draw_payload(lines, invert_header=invert)

    async def _maybe_render(self) -> None:
        m = self._model
        if not m.connected or m.busy:
            return  # no board, or a commission owns the wire (it draws itself)
        payload = self._frame(self._current_view())
        if payload == self._last_payload and self._initialized and not self._absent:
            return  # coalesce: nothing changed
        await self._draw(self._session, payload)

    # --- the live commission arc (called by CommissionRunner under exclusive) --

    async def draw_commission(
        self,
        board: _Execer,
        *,
        slug: str,
        display_name: str,
        attempt: int,
        max_attempts: int,
        stage: str | None,
        status: str | None,
        outcome: str | None = None,
        fail_reason: str | None = None,
    ) -> None:
        """Draw one commission frame through the loop's own board handle. The
        stage is passed explicitly (not read off the async model) so it is
        race-free with the event the loop is publishing right now."""
        lines, invert = agent_lines(
            connected=True,
            driver_count=self._model.driver_count,
            active=True,
            slug=slug,
            display_name=display_name,
            attempt=attempt,
            max_attempts=max_attempts,
            stage=stage,
            status=status,
            outcome=outcome,
            fail_reason=fail_reason,
        )
        await self._draw(board, draw_payload(lines, invert_header=invert))

    # --- the wire (init + draw + self-heal) ----------------------------------

    async def _draw(self, execer: _Execer, payload: str) -> None:
        if self._absent and time.monotonic() < self._retry_at:
            return
        if not self._initialized and not await self._init(execer):
            return
        res = await execer.exec(payload, self._settings.exec_timeout_s)
        if res.timed_out:
            return
        if res.stderr:
            if is_uninitialized_error(res.stderr):
                # A soft_reset wiped `_oled`; re-init and redraw once.
                self._initialized = False
                if await self._init(execer):
                    res = await execer.exec(payload, self._settings.exec_timeout_s)
                    if res.ok:
                        self._last_payload = payload
                return
            # OLED not on the bus (or wiring fault): back off, don't spam.
            self._mark_absent()
            return
        self._last_payload = payload

    async def _init(self, execer: _Execer) -> bool:
        payload = build_init_payload(
            self._settings.pins_i2c_sda,
            self._settings.pins_i2c_scl,
            self._settings.i2c_addr_oled,
        )
        res = await execer.exec(payload, self._settings.exec_timeout_s)
        if res.timed_out or res.stderr:
            self._mark_absent()
            return False
        self._initialized = True
        self._absent = False
        self._last_payload = None  # force a fresh draw after (re)init
        return True

    def _mark_absent(self) -> None:
        self._absent = True
        self._initialized = False
        self._retry_at = time.monotonic() + 30.0
