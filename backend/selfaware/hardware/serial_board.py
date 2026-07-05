"""SerialBoard — raw-REPL transport over pyserial (the real Pico W).

Blocking serial I/O runs in a worker thread (asyncio.to_thread); the HOST
timeout is asyncio.wait_for AROUND the thread. The `_exec_blocking` byte dance
and every non-negotiable it encodes are below.

pyserial is imported LAZILY inside methods: the test suite must be able to
import this module (and the whole package) without ever touching a port.
Exactly ONE SerialBoard instance exists per process (enforced by the api/
lifespan) — a second port owner throws 'device busy' and burns an hour.
"""

import asyncio
import time

from selfaware.hardware.base import BoardConnectError, ExecResult
from selfaware.hardware.raw_repl import (
    CTRL_A,
    CTRL_B,
    CTRL_C,
    CTRL_D,
    EOT,
    OK_MARKER,
    RAW_PROMPT,
    RxBuffer,
    parse_exec_reply,
)

_PROMPT_MARKER = b">"  # the raw-REPL "ready" prompt trailing every exec reply
_CONNECT_PROMPT_TIMEOUT_S = 4.0  # under the session's connect_timeout_s (5s)
_SOFT_RESET_PROMPT_TIMEOUT_S = 4.0


class SerialBoard:
    """BoardTransport implementation for a real MicroPython board.

    Non-negotiables encoded here (agentic-hardware-bringup methodology):
      * DTR/RTS suppression: construct serial.Serial() UNOPENED, set
        .dtr = False and .rts = False, THEN open — opening a port asserts
        DTR/RTS by default and on many boards that RESETS THE CHIP, so the
        handshake races a rebooting board ('flaky USB' that isn't).
      * Address by stable id ('/dev/cu.usbmodem<serial>' via
        discovery.find_board_port), never an enumerated index.
      * Short serial read timeout (~50ms) pumping chunks into RxBuffer;
        parse by token search, never fixed-size reads.
      * On connect: CTRL-C x2 to interrupt any boot program BEFORE CTRL-A.
      * Consume the trailing '>' prompt after every exec reply, or it
        pollutes the next read.
      * A timed-out worker thread keeps writing to the line — the dirty-line
        bit records that, and the next exec must refuse to run until
        soft_reset() has resynced.
    """

    def __init__(self, port_id: str, baud: int = 115200, read_timeout_s: float = 0.05) -> None:
        self.port_id = port_id
        self.is_mock = False
        self._baud = baud
        self._read_timeout_s = read_timeout_s
        self._serial = None  # serial.Serial | None — created lazily in connect()
        self._connected = False
        self._dirty = False  # set on host timeout: the line has unconsumed bytes in flight
        self._rx = RxBuffer()

    @property
    def connected(self) -> bool:
        return self._connected

    # --- connect ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the port and enter raw REPL. Idempotent. Raises BoardConnectError."""
        if self._connected:
            return
        await asyncio.to_thread(self._connect_blocking)

    def _connect_blocking(self) -> None:
        import serial  # lazy — importing this module must never touch a port

        if not self.port_id:
            raise BoardConnectError(
                "no serial port resolved — board absent (check the USB *data* cable / "
                "host USB, not just a power LED), or set SELFAWARE_BOARD_PORT explicitly"
            )
        try:
            s = serial.Serial()
            s.port = self.port_id
            s.baudrate = self._baud
            s.timeout = self._read_timeout_s
            s.dtr = False  # suppress the auto-reset on open (DTR/RTS assert = chip reset)
            s.rts = False
            s.open()
        except serial.SerialException as exc:  # type: ignore[attr-defined]
            msg = str(exc).lower()
            if any(tok in msg for tok in ("busy", "resource", "access is denied", "errno 16", "permission")):
                raise BoardConnectError(
                    f"port {self.port_id} is busy — another owner holds it "
                    f"(disable your IDE's MicroPython auto-connect): {exc}"
                ) from exc
            raise BoardConnectError(f"cannot open {self.port_id}: {exc}") from exc

        self._serial = s
        try:
            self._enter_raw(timeout_s=_CONNECT_PROMPT_TIMEOUT_S)
        except TimeoutError as exc:
            with_close = getattr(s, "close", None)
            if with_close is not None:
                try:
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
            self._serial = None
            raise BoardConnectError(
                f"opened {self.port_id} but never saw the raw-REPL prompt "
                f"(wrong baud, or a boot program is holding the line): {exc}"
            ) from exc
        self._connected = True

    def _enter_raw(self, timeout_s: float) -> None:
        """CTRL-C x2 (break the boot program) -> CTRL-A -> wait for RAW_PROMPT."""
        s = self._serial
        assert s is not None
        s.write(CTRL_C + CTRL_C)  # interrupt any running main.py BEFORE entering raw
        time.sleep(0.1)
        s.reset_input_buffer()
        self._rx.clear()
        s.write(b"\r" + CTRL_A)  # enter raw REPL
        self._pump_until(RAW_PROMPT, time.monotonic() + timeout_s)
        self._rx.clear()  # nothing follows the prompt on a fresh enter

    # --- exec ---------------------------------------------------------------------

    async def exec(self, code: str, timeout_s: float) -> ExecResult:
        """One raw-REPL execution with the HOST watchdog.

        The inner _exec_blocking gives up at `started + timeout_s` on its own, so
        the thread terminates instead of leaking; asyncio.wait_for at a slightly
        larger bound is the backstop for a truly wedged serial read. Either way a
        timeout sets the dirty bit — nothing may exec until soft_reset resyncs.
        """
        if self._serial is None or not self._connected:
            return ExecResult(stdout="", stderr="board not connected", duration_s=0.0)
        if self._dirty:
            await self.soft_reset()  # resync before touching the line

        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._exec_blocking, code, started, timeout_s),
                timeout_s + 0.5,
            )
        except (TimeoutError, asyncio.TimeoutError):
            self._dirty = True  # the thread may STILL be writing; refuse until soft_reset
            return ExecResult(stdout="", stderr="", duration_s=time.monotonic() - started, timed_out=True)
        if result.timed_out:
            self._dirty = True
        return result

    def _exec_blocking(self, code: str, started: float, timeout_s: float) -> ExecResult:
        """The byte dance, in the worker thread:

          1. write code bytes + CTRL-D
          2. take_until(OK_MARKER)      — board ack
          3. take_until(EOT)            -> stdout bytes
          4. take_until(EOT)            -> stderr bytes (VERBATIM traceback)
          5. consume the trailing b'>'  — or the next read is polluted
          6. parse_exec_reply(...)

        Keep prints tiny: host-bound stdout silently truncates past a few
        hundred bytes on RP2040 USB-CDC — chunk+hash for anything bulky.
        """
        deadline = started + timeout_s
        s = self._serial
        assert s is not None
        try:
            s.write(code.encode("utf-8") + CTRL_D)
            self._pump_until(OK_MARKER, deadline)
            stdout_b = self._pump_until(EOT, deadline)
            stderr_b = self._pump_until(EOT, deadline)
        except TimeoutError:
            # Partial reply on the wire; the line is dirty. The async layer sets
            # the dirty bit off the timed_out result and soft_reset drains it.
            return ExecResult(stdout="", stderr="", duration_s=time.monotonic() - started, timed_out=True)
        # Trailing prompt: best-effort. If it hasn't arrived, the next exec's
        # OK-pump discards it — never fail a good read over the '>'.
        try:
            self._pump_until(_PROMPT_MARKER, min(deadline, time.monotonic() + 0.5))
        except TimeoutError:
            pass
        return parse_exec_reply(stdout_b, stderr_b, time.monotonic() - started)

    def _pump_until(self, marker: bytes, deadline: float) -> bytes:
        """Read chunks into RxBuffer until `marker` lands; return bytes before it.

        Token search, never fixed-size reads (RxBuffer keeps the tail past the
        marker for the next call). Raises TimeoutError past `deadline`.
        """
        s = self._serial
        assert s is not None
        while True:
            found = self._rx.take_until(marker)
            if found is not None:
                return found
            if time.monotonic() > deadline:
                raise TimeoutError(f"raw-REPL: no {marker!r} before deadline; buf={self._rx.peek()[:160]!r}")
            chunk = s.read(512)
            if chunk:
                self._rx.feed(chunk)

    # --- recovery -----------------------------------------------------------------

    async def soft_reset(self) -> None:
        """The guaranteed escape hatch: CTRL-C x2 -> CTRL-B -> CTRL-D -> re-enter raw.

        Host-owned recovery — generated code never gets to decide whether the
        board resets. Clears the dirty bit only on a successful re-sync.
        """
        if self._serial is None:
            return
        await asyncio.to_thread(self._soft_reset_blocking)
        self._dirty = False

    def _soft_reset_blocking(self) -> None:
        s = self._serial
        assert s is not None
        s.reset_input_buffer()
        self._rx.clear()
        s.write(CTRL_C + CTRL_C)  # break whatever is running / drain in-flight code
        time.sleep(0.1)
        s.write(CTRL_B)  # leave raw -> friendly REPL
        time.sleep(0.1)
        s.write(CTRL_D)  # soft-reset the interpreter: clean module/peripheral state
        time.sleep(0.25)  # let it reboot and (maybe) start main.py
        s.write(CTRL_C + CTRL_C)  # break any main.py that just launched
        time.sleep(0.1)
        s.reset_input_buffer()
        self._rx.clear()
        s.write(b"\r" + CTRL_A)  # re-enter raw REPL
        self._pump_until(RAW_PROMPT, time.monotonic() + _SOFT_RESET_PROMPT_TIMEOUT_S)
        self._rx.clear()

    async def close(self) -> None:
        """Leave raw REPL (CTRL-B, best-effort) and release the port."""
        if self._serial is not None:
            await asyncio.to_thread(self._close_blocking)
        self._connected = False

    def _close_blocking(self) -> None:
        s = self._serial
        if s is None:
            return
        try:
            s.write(CTRL_B)  # back to friendly REPL so the next opener isn't stuck in raw
        except Exception:  # noqa: BLE001
            pass
        try:
            s.close()
        except Exception:  # noqa: BLE001
            pass
        self._serial = None


__all__ = ["BoardConnectError", "SerialBoard"]
