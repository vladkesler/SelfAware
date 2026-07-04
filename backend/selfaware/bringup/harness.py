"""HOST-authored harness payloads — the LLM never writes the test call.

Invariant #2: DriverGenOutput has no read_call field. The host appends the
constrained call itself, so the model can never smuggle behavior into the
test stage, and the last stdout line is — by construction — THE reading.

Keep prints tiny: host-bound REPL stdout silently truncates past a few
hundred bytes on RP2040 USB-CDC (data loss that masquerades as a board bug).
"""

from selfaware.bringup.models import BringupSpec
from selfaware.hardware.base import ExecResult


class ReadingParseError(Exception):
    """The driver ran without a traceback but its output is not a number.

    Treated as a failed attempt with an honest reason fed back to the model —
    never a crash of the loop.
    """


def build_read_payload(driver_code: str, spec: BringupSpec | None = None) -> str:
    """driver_code + the one constrained read call. Last stdout line == reading.

    `spec` is accepted for signature stability (per-class variations land
    build day, e.g. unit scaling notes); day-1 the call is identical for all
    sensor classes.
    """
    return driver_code.rstrip("\n") + "\nprint(Driver().read())\n"


def build_output_payload(driver_code: str, spec: BringupSpec, verify_code: str | None = None) -> str:
    """ONE exec that drives the actuator with a guaranteed-off path.

    verify_code=None (day-1, soft verify): instantiate, set(1), set(0) in a
    finally — 'it loads and runs without a traceback'. The trailing print(0)
    keeps the last-line convention parseable.

    verify_code=<another driver's source> (cross-modal, build day wiring):
    the verifier class is captured under an alias BEFORE the actuator
    redefines `Driver`, then ambient and driven samples run in the SAME exec
    so the output stays driven while sampled (no GC race between execs).
    set(0) stays in the finally — assume stateful outputs LATCH.
    """
    driver_code = driver_code.rstrip("\n")
    if verify_code is None:
        return (
            f"{driver_code}\n"
            "_act = Driver()\n"
            "try:\n"
            "    _act.set(1)\n"
            "finally:\n"
            "    _act.set(0)\n"
            "print(0)\n"
        )
    return (
        f"{verify_code.rstrip(chr(10))}\n"
        "_Verify = Driver\n"
        f"{driver_code}\n"
        "_act = Driver()\n"
        "_sense = _Verify()\n"
        "_ambient = [_sense.read() for _ in range(3)]\n"
        "try:\n"
        "    _act.set(1)\n"
        "    _driven = [_sense.read() for _ in range(3)]\n"
        "finally:\n"
        "    _act.set(0)\n"
        "print(_ambient)\n"
        "print(_driven)\n"
    )


def parse_reading(result: ExecResult) -> float:
    """result.last_line -> float, or ReadingParseError with an honest reason."""
    line = result.last_line
    if not line:
        raise ReadingParseError("driver produced no stdout — nothing to read")
    try:
        return float(line)
    except ValueError as exc:
        raise ReadingParseError(f"last stdout line is not a number: {line!r}") from exc
