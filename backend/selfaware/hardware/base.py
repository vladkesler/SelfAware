"""BoardTransport + ExecResult — the seam that makes hardware optional.

SerialBoard (real Pico over USB) and MockBoard (scripted/simulated) both
implement `BoardTransport`, so every layer above runs identically with or
without silicon. `ExecResult.stderr` is sacred: non-empty stderr IS the
verbatim MicroPython traceback, the one signal that cannot be hallucinated —
it flows untouched into commission.traceback events and repair prompts.
"""

import time
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class BoardConnectError(Exception):
    """Raised by connect() when the link cannot be established.

    Distinguishes 'no device enumerated' from 'device busy' (another process
    owns the port — usually an IDE's auto-connect) in its message, because
    those two failures have opposite fixes.
    """


class ExecResult(BaseModel):
    """Outcome of one raw-REPL exec.

    Conventions the whole system leans on:
      * stderr non-empty == VERBATIM board traceback (never paraphrased upstream)
      * the last non-empty stdout line is THE reading (boards emit banners/noise)
      * timed_out=True means the HOST watchdog fired; the caller must assume a
        dirty line and soft_reset before the next exec.
    """

    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        """True iff no traceback and the host watchdog did not fire."""
        return not self.stderr and not self.timed_out

    @property
    def last_line(self) -> str:
        """Last non-empty stdout line — by convention, the reading."""
        for line in reversed(self.stdout.splitlines()):
            stripped = line.strip()
            if stripped:
                return stripped
        return ""


def exec_result(stdout: str, stderr: str, started_at: float, *, timed_out: bool = False) -> ExecResult:
    """Convenience constructor stamping duration from a time.monotonic() start."""
    return ExecResult(
        stdout=stdout,
        stderr=stderr,
        duration_s=time.monotonic() - started_at,
        timed_out=timed_out,
    )


@runtime_checkable
class BoardTransport(Protocol):
    """Async board access. Implementations: SerialBoard, MockBoard.

    Only hardware/ sees this interface; everyone else goes through
    BoardSession (the single lock lives there, not here — transports are
    dumb pipes and must never grow their own concurrency policy).
    """

    port_id: str  # stable identifier: '/dev/cu.usbmodem<serial>' or 'mock://demo'
    is_mock: bool

    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None:
        """Open the link and enter raw REPL. Idempotent. Raises BoardConnectError."""
        ...

    async def exec(self, code: str, timeout_s: float) -> ExecResult:
        """Execute a code string via raw REPL. The HOST timeout wraps the whole
        exchange; on timeout return ExecResult(timed_out=True) — the caller
        decides to soft_reset."""
        ...

    async def soft_reset(self) -> None:
        """CTRL-C x2 -> CTRL-B -> CTRL-D -> re-enter raw REPL. The guaranteed
        escape hatch after a hang or a wedged line."""
        ...

    async def close(self) -> None: ...
