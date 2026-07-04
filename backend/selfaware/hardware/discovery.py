"""Port discovery + HOST-authored probe snippets + the known-device table.

Plug-and-detect, the honest version (docs/hardware-bringup.md):
  * I2C devices announce an ADDRESS -> true identification via
    KNOWN_I2C_DEVICES -> discovery.device_found{confidence: "exact"}.
  * A raw ADC voltage can NEVER reveal the part (information theory, not a
    missing feature) -> presence-change detection only, confidence "unknown",
    and a human names it (the "teach it once" step).

Both probe snippets are HOST-authored constants — the LLM never writes scan
code, because discovery must be deterministic (host/LLM split, invariant #2).
"""

from typing import Any


async def find_board_port(glob_pattern: str) -> str | None:
    """Resolve the stable port id for board_port='auto'.

    Build-day job: glob.glob(pattern) (e.g. '/dev/cu.usbmodem*' on macOS,
    '/dev/serial/by-id/*' on Linux) -> first match, or None when nothing
    enumerates. Must distinguish 'no device enumerated' (absent from the OS
    device list — check cable/host USB before code) from 'device busy'
    (a second owner, usually an IDE auto-connect) in the error path, because
    the fixes are opposite. Never returns an enumerated index.
    """
    raise NotImplementedError("build day: glob -> stable port id; distinguish absent vs busy")


# Format with .format(sda=..., scl=...). One tiny print — REPL stdout is for
# small reads only (silent truncation past a few hundred bytes on RP2040).
I2C_SCAN_SNIPPET = (
    "from machine import I2C, Pin\n"
    "print(I2C(0, sda=Pin({sda}), scl=Pin({scl})).scan())\n"
)

# Format with .format(pin=...). Prints a small sample list; the host classifies
# the signature (see DiscoveryWatcher._classify_adc) — the board just samples.
ADC_SIGNATURE_SNIPPET = (
    "from machine import ADC\n"
    "import time\n"
    "adc = ADC({pin})\n"
    "s = []\n"
    "for _ in range(8):\n"
    "    s.append(adc.read_u16())\n"
    "    time.sleep_ms(5)\n"
    "print(s)\n"
)

# addr -> identity + pre-filled BringupSpec fields (suggested_spec rides the
# discovery.device_found payload so the UI can offer one-click commission).
# Addresses are the PicoBricks bench reality; extend freely on build day.
KNOWN_I2C_DEVICES: dict[int, dict[str, Any]] = {
    0x3C: {
        "identity": "SSD1306 OLED 128x64",
        "suggested_spec": {
            "slug": "oled",
            "display_name": "OLED display (SSD1306)",
            "protocol_class": "digital_bus",
            "i2c_addr": 0x3C,
            "extra_context": "Display, not a sensor — commission as output-ish bus device (build day).",
        },
    },
    0x70: {
        "identity": "SHTC3 temperature/humidity",
        "suggested_spec": {
            "slug": "shtc3",
            "display_name": "SHTC3 temperature/humidity",
            "protocol_class": "digital_bus",
            "i2c_addr": 0x70,
            "expected_min": -10,
            "expected_max": 60,
            "unit": "degC",
            "stimulus_hint": "breathe on the sensor",
            "extra_context": "Command-based part (wakeup 0x3517, measure 0x7CA2): command WRITES, not register reads.",
        },
    },
    0x22: {
        "identity": "PicoBricks motor driver (I2C revision)",
        "suggested_spec": {
            "slug": "motor",
            "display_name": "DC motor (I2C driver)",
            "protocol_class": "output",
            "i2c_addr": 0x22,
            "extra_context": (
                "Only on I2C-motor board revisions (others drive GP21/GP22 directly). "
                "Stateful co-processor: assume outputs LATCH — guaranteed set(0) path, ramp don't slam."
            ),
        },
    },
}
