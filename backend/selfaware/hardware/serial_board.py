"""SerialBoard — raw-REPL transport over pyserial (the real Pico W).

Blocking serial I/O runs in a worker thread (asyncio.to_thread); the HOST
timeout is asyncio.wait_for AROUND the thread. Build-day job for this module
is the `_exec_blocking` byte dance; every non-negotiable it must encode is
written into the stubs below so the 2 a.m. implementer doesn't have to
rediscover them.

pyserial is imported LAZILY inside methods: the test suite must be able to
import this module (and the whole package) without ever touching a port.
Exactly ONE SerialBoard instance exists per process (enforced by the api/
lifespan in PR3) — a second port owner throws 'device busy' and burns an hour.
"""

from selfaware.hardware.base import BoardConnectError, ExecResult


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

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Open the port and enter raw REPL. Idempotent.

        Build-day sequence (all inside to_thread; wait_for from the caller):
          1. import serial (lazy);  s = serial.Serial()  # UNOPENED
          2. s.port/baudrate/timeout = ...; s.dtr = False; s.rts = False
          3. s.open()  — 'device busy' here -> BoardConnectError naming the
             likely cause (IDE auto-connect owns the port)
          4. write CTRL-C x2 (break the boot program), drain
          5. write b'\\r' + CTRL-A; pump RxBuffer until RAW_PROMPT
          6. clear the buffer; self._connected = True
        """
        raise NotImplementedError("build day: DTR/RTS=False before open, CTRL-Cx2, CTRL-A, wait RAW_PROMPT")

    async def exec(self, code: str, timeout_s: float) -> ExecResult:
        """One raw-REPL execution with the HOST watchdog.

        Build-day shape:
            if self._dirty: await self.soft_reset()   # resync before touching the line
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._exec_blocking, code), timeout_s)
            except TimeoutError:
                self._dirty = True   # the thread is STILL writing; nothing may
                                     # exec until soft_reset drains + resyncs
                return ExecResult(stdout="", stderr="", duration_s=timeout_s, timed_out=True)

        Note: cancelling the wait does NOT stop the blocking thread — that is
        exactly why the dirty bit exists and why BoardSession serializes all
        access behind THE lock.
        """
        raise NotImplementedError("build day: wait_for(to_thread(_exec_blocking)) + dirty-line bit")

    def _exec_blocking(self, code: str) -> ExecResult:
        """The byte dance, in the worker thread (build day):

          1. write code bytes + CTRL-D
          2. pump RxBuffer: take_until(OK_MARKER)      — board ack
          3. take_until(EOT)                            -> stdout bytes
          4. take_until(EOT)                            -> stderr bytes (VERBATIM traceback)
          5. consume the trailing b'>' prompt           — or the next read is polluted
          6. return raw_repl.parse_exec_reply(stdout, stderr, duration)

        Keep prints tiny: host-bound stdout silently truncates past a few
        hundred bytes on RP2040 USB-CDC — chunk+hash for anything bulky.
        """
        raise NotImplementedError("build day: CTRL-D, OK, stdout-EOT, stderr-EOT, trailing '>'")

    async def soft_reset(self) -> None:
        """The guaranteed escape hatch: CTRL-C x2 -> CTRL-B -> CTRL-D -> re-enter raw.

        Build day: run in to_thread, clear RxBuffer, clear self._dirty on
        success. This is host-owned recovery — generated code never gets to
        decide whether the board resets.
        """
        raise NotImplementedError("build day: CTRL-Cx2, CTRL-B, CTRL-D, re-enter raw REPL, clear dirty bit")

    async def close(self) -> None:
        """Leave raw REPL (CTRL-B, best-effort) and release the port."""
        raise NotImplementedError("build day: best-effort CTRL-B then serial close")


__all__ = ["BoardConnectError", "SerialBoard"]
