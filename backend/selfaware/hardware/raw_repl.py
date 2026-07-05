"""MicroPython raw-REPL protocol: framing constants + the stateful RxBuffer.

This module is PURE (no I/O) so the token parsing that the whole loop depends
on is unit-testable with zero hardware. The framing (public MicroPython
protocol — rediscovering these strings at midnight is the classic hour-burner):

    enter:  CTRL-C x2 (break any boot program), then b'\\r' + CTRL-A,
            wait for the literal RAW_PROMPT
    exec:   code + CTRL-D  ->  b'OK' + stdout + EOT + stderr + EOT + b'>'
    NOTE:   the trailing '>' MUST be consumed or it pollutes the next read.

The stdout/EOT/stderr/EOT separation is the mechanism the self-repair loop
depends on: non-empty stderr IS the verbatim traceback fed back to the model.
Parse by searching the buffer for tokens, never by fixed-size reads.
"""

from selfaware.hardware.base import ExecResult

CTRL_A = b"\x01"  # enter raw REPL
CTRL_B = b"\x02"  # exit raw REPL (back to friendly)
CTRL_C = b"\x03"  # keyboard interrupt (x2 on connect to break the boot program)
CTRL_D = b"\x04"  # in raw mode: execute; in friendly mode: soft reset
EOT = b"\x04"  # frame separator in the exec reply
OK_MARKER = b"OK"  # board's two-byte ack after CTRL-D
RAW_PROMPT = b"raw REPL; CTRL-B to exit\r\n>"


class RxBuffer:
    """Stateful receive buffer for a byte stream with no message boundaries.

    The invariant that earns this class its tests: bytes arriving PAST a
    matched marker belong to the NEXT read — never discard the tail. The
    serial reader pumps chunks in via feed() (short ~50ms read timeout) and
    the protocol layer pulls frames out via take_until().
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        """Append newly arrived bytes (any chunking, including mid-marker)."""
        self._buf.extend(data)

    def take_until(self, marker: bytes) -> bytes | None:
        """Return the bytes BEFORE the first occurrence of `marker`, consuming
        both, or None if the marker has not fully arrived yet.

        A marker split across feed() calls matches once its last byte lands.
        Bytes after the marker stay buffered for the next call.
        """
        if not marker:
            raise ValueError("marker must be non-empty")
        idx = self._buf.find(marker)
        if idx < 0:
            return None
        head = bytes(self._buf[:idx])
        del self._buf[: idx + len(marker)]
        return head

    def clear(self) -> None:
        """Drop everything buffered (used on connect/soft-reset resync)."""
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

    def peek(self) -> bytes:
        """Non-consuming view — debugging/tests only."""
        return bytes(self._buf)


def parse_exec_reply(stdout_bytes: bytes, stderr_bytes: bytes, duration_s: float) -> ExecResult:
    """Decode the two EOT-framed sections into an ExecResult.

    Decode with errors='replace' (never raise on a stray byte), normalize
    CRLF -> LF on both streams (the board's USB-CDC line endings are noise, not
    signal). stderr is otherwise kept byte-faithful — it is the VERBATIM
    traceback and must round-trip into repair prompts and the UI untouched.
    """
    stdout = stdout_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n")
    stderr = stderr_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return ExecResult(stdout=stdout, stderr=stderr, duration_s=duration_s)
