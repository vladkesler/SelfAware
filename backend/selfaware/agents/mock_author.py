"""Mock author — the canned fail->repair->pass storyteller. ZERO model calls.

This is what SELFAWARE_MOCK_AUTHOR=true wires into the loop's author seam, and
it pairs with hardware.mock_board.demo_fail_then_pass_script():

  attempt 1: gate-PASSING analog code with the classic wrong-platform habit —
             it calls ESP32's `adc.read()`, which does not exist on RP2040
             MicroPython. The static gate cannot know that (`read` is a
             perfectly legal attribute name), so the code reaches the "board",
             where the demo script answers with the exact AttributeError a
             real Pico would raise. This mirrors the real-hardware demo beat.
  attempt 2: the same driver with the correct `read_u16()`; the script answers
             a plausible reading, plausibility passes, the driver registers.

Together they make `make demo-mock` the full theater with no hardware and no
API key (the flagship demo must never depend on credentials). The reasoning
strings ARE the narration — they land in the UI via agent.thought.
"""

import asyncio

from selfaware.bringup.models import BringupSpec, DriverGenOutput
from selfaware.config import Settings

_DRIVER_ESP32_HABIT = """\
import machine
import time

class Driver:
    def __init__(self):
        self.adc = machine.ADC({pin})

    def read(self):
        total = 0
        for _ in range(8):
            total += self.adc.read()
            time.sleep_ms(1)
        return total // 8
"""

_DRIVER_CORRECTED = """\
import machine
import time

class Driver:
    def __init__(self):
        self.adc = machine.ADC({pin})

    def read(self):
        total = 0
        for _ in range(8):
            total += self.adc.read_u16()
            time.sleep_ms(1)
        return total // 8
"""


def build_mock_author(settings: Settings):
    """Return a loop-seam-compatible author ((spec, attempt_n, last_error) ->
    DriverGenOutput) serving the canned two-beat sequence.

    Keyed on attempt_n, not internal state, so a re-run of the demo (or a
    re-commission) replays the same story deterministically.

    settings.mock_pace_s (0 in tests) is slept before every attempt's output —
    a real model thinks for seconds, and the UI narration needs that beat.
    """
    pace = settings.mock_pace_s

    async def author(spec: BringupSpec, attempt_n: int, last_error: str | None) -> DriverGenOutput:
        if pace > 0:
            await asyncio.sleep(pace)  # theatrical "the model is thinking" beat
        target = spec.pins.get("adc", settings.adc_capable_pins[0])
        if attempt_n == 1:
            return DriverGenOutput(
                reasoning=(
                    f"{spec.display_name} is a plain analog device, so this is one ADC "
                    f"channel on GP{target}. Sampling 8x with 1ms spacing and averaging "
                    "with adc.read() to smooth out noise."
                ),
                driver_code=_DRIVER_ESP32_HABIT.format(pin=target),
                imports_used="machine, time",
            )
        return DriverGenOutput(
            reasoning=(
                "The board replied: AttributeError — 'ADC' object has no attribute "
                "'read'. That is the ESP32 ADC API; RP2040 MicroPython exposes "
                "read_u16(). Same averaged read, corrected method call."
            ),
            driver_code=_DRIVER_CORRECTED.format(pin=target),
            imports_used="machine, time",
        )

    return author
