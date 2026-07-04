"""BoardSession — THE single asyncio.Lock, and everything it guards.

One serial line, one lock (invariant #3). The telemetry poller, every tool
call, every scan, and the commission loop all share one wire; without a
single lock they interleave and corrupt raw-REPL framing. Nothing outside
hardware/ ever receives the raw transport — BoardSession is what everyone
else is handed.

The subtle rule this module exists to encode: cancelling an asyncio task does
NOT interrupt a blocking call already running in a worker thread — the worker
keeps writing to the line. So pausing the poller for an exclusive op is
acquire the lock (drains any in-flight exec) -> THEN cancel -> THEN reap.
That ordering is pure asyncio, so it is implemented for real here, today, and
works against MockBoard.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from selfaware.bringup.harness import ReadingParseError, build_read_payload, parse_reading
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.payloads import (
    BoardConnectedPayload,
    BoardDisconnectedPayload,
    BoardStatusPayload,
    SensorReadingPayload,
)
from selfaware.events.types import EventType
from selfaware.hardware.base import BoardTransport, ExecResult

if TYPE_CHECKING:
    from selfaware.registry.store import DriverRegistry


class BoardSession:
    """The single owner of board access. Everyone else goes through here."""

    def __init__(
        self,
        transport: BoardTransport,
        bus: EventBus,
        settings: Settings,
        registry: "DriverRegistry | None" = None,
    ) -> None:
        self._transport = transport
        self._bus = bus
        self._settings = settings
        self._registry = registry  # optional: the poller idles without one
        self._lock = asyncio.Lock()  # THE lock. The only one, process-wide.
        self._poller_task: asyncio.Task[None] | None = None
        self._poller_interval = settings.poller_interval_s
        self._busy = False  # true while exclusive() holds the lock (UI: "commissioning")

    # --- wiring -----------------------------------------------------------------

    def bind_registry(self, registry: "DriverRegistry") -> None:
        """Late-bind the registry (lifespan builds session before registry)."""
        self._registry = registry

    @property
    def transport(self) -> BoardTransport:
        """Escape hatch for hardware/ internals only (watcher, tests).

        Everything outside hardware/ MUST use exec()/exclusive() — reaching
        for the raw transport bypasses THE lock and corrupts framing.
        """
        return self._transport

    # --- lifecycle ----------------------------------------------------------------

    async def connect(self) -> None:
        """Best-effort connect; emits board.connected or board.disconnected.

        Never raises: board absent => stay honestly disconnected (invariant #4
        — no silent mock fallback lives here or anywhere).
        """
        try:
            await asyncio.wait_for(self._transport.connect(), self._settings.connect_timeout_s)
        except Exception as exc:  # noqa: BLE001 — boot must not die on a missing board
            self._bus.publish(
                EventType.BOARD_DISCONNECTED,
                BoardDisconnectedPayload(reason=f"{type(exc).__name__}: {exc}"),
            )
            self._emit_board_status()
            return
        self._bus.publish(
            EventType.BOARD_CONNECTED,
            BoardConnectedPayload(port_id=self._transport.port_id, mock=self._transport.is_mock),
        )
        self._emit_board_status()

    async def close(self) -> None:
        await self.stop_poller()
        await self._transport.close()

    # --- serialized access -----------------------------------------------------------

    async def exec(self, code: str, timeout_s: float | None = None) -> ExecResult:
        """Lock-acquiring exec for ad-hoc callers (tools, scans, cmd.read).

        Timeout -> soft_reset BEFORE releasing the lock, so the next caller
        inherits a clean line, always. This policy is host-owned and lives
        here exactly once.
        """
        timeout = timeout_s if timeout_s is not None else self._settings.exec_timeout_s
        async with self._lock:
            result = await self._transport.exec(code, timeout)
            if result.timed_out:
                await self._transport.soft_reset()
            return result

    @contextlib.asynccontextmanager
    async def exclusive(self) -> AsyncIterator["ExclusiveBoard"]:
        """Pause-under-lock: the only sanctioned way to own the wire outright.

        Ordering is load-bearing:
          1. acquire THE lock      — drains any in-flight poller exec (a
                                     cancelled task does not stop a blocking
                                     thread; the lock waits it out)
          2. cancel the poller     — no new polls can start
          3. reap it               — await the cancellation
          4. yield ExclusiveBoard  — direct transport access, lock still held
          5. finally: release, restart the poller if it was running

        Emits board.status{busy} on enter/exit so the UI shows commissioning.
        """
        await self._lock.acquire()
        poller_was_running = self._poller_task is not None
        try:
            if self._poller_task is not None:
                self._poller_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._poller_task
                self._poller_task = None
            self._busy = True
            self._emit_board_status()
            yield ExclusiveBoard(self._transport, self._lock, self._settings)
        finally:
            self._busy = False
            self._emit_board_status()
            self._lock.release()
            if poller_was_running:
                await self.start_poller(self._poller_interval)

    # --- telemetry poller ---------------------------------------------------------------

    async def start_poller(self, interval_s: float | None = None) -> None:
        """Idempotent. Each poll runs UNDER the lock; between polls it sleeps
        unlocked, so tools and commissions are never starved."""
        if self._poller_task is not None:
            return
        if interval_s is not None:
            self._poller_interval = interval_s
        self._poller_task = asyncio.create_task(self._poll_loop(), name="selfaware-poller")

    async def stop_poller(self) -> None:
        if self._poller_task is None:
            return
        self._poller_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._poller_task
        self._poller_task = None

    @property
    def poller_running(self) -> bool:
        return self._poller_task is not None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — telemetry must never kill itself
                # Build day: log via observability; a failed poll is not an event.
                pass
            await asyncio.sleep(self._poller_interval)

    async def _poll_once(self) -> None:
        """Read every ACTIVE sensor through its own verified driver + harness.

        Skips silently with no registry, no drivers, or no link — the poller
        is ambience, not a health check. Works against MockBoard TODAY: the
        exec'd driver code hits the simulated generators.
        """
        if self._registry is None or not self._transport.connected:
            return
        for record in self._registry.sensors():
            payload = build_read_payload(record.driver_code)
            async with self._lock:
                result = await self._transport.exec(payload, self._settings.exec_timeout_s)
                if result.timed_out:
                    await self._transport.soft_reset()
                    continue
            if not result.ok:
                continue  # a poll traceback is noise, not a commission failure
            try:
                value = parse_reading(result)
            except ReadingParseError:
                continue
            record.last_reading = value
            record.last_read_at = datetime.now(UTC)
            self._bus.publish(
                EventType.SENSOR_READING,
                # plausible=True day-1: DriverRecord carries no expected window
                # yet; the host plausibility verdict wires in on build day.
                SensorReadingPayload(slug=record.slug, value=value, unit=record.unit, plausible=True),
            )

    # --- helpers ------------------------------------------------------------------------

    def board_status(self) -> BoardStatusPayload:
        return BoardStatusPayload(
            connected=self._transport.connected,
            port_id=self._transport.port_id,
            mock=self._transport.is_mock,
            busy=self._busy,
        )

    def _emit_board_status(self) -> None:
        self._bus.publish(EventType.BOARD_STATUS, self.board_status())


class ExclusiveBoard:
    """Direct transport handle, valid ONLY inside session.exclusive().

    exec/soft_reset go straight to the transport — the lock is already held,
    so calling session.exec() from in here would deadlock. A debug guard
    asserts the lock is actually held on every call.
    """

    def __init__(self, transport: BoardTransport, lock: asyncio.Lock, settings: Settings) -> None:
        self._transport = transport
        self._lock = lock
        self._settings = settings

    async def exec(self, code: str, timeout_s: float | None = None) -> ExecResult:
        assert self._lock.locked(), "ExclusiveBoard used outside session.exclusive()"
        timeout = timeout_s if timeout_s is not None else self._settings.exec_timeout_s
        return await self._transport.exec(code, timeout)

    async def soft_reset(self) -> None:
        assert self._lock.locked(), "ExclusiveBoard used outside session.exclusive()"
        await self._transport.soft_reset()
