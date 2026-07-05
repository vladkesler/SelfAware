"""Host-authored SSD1306 render payloads — the device narrates itself.

These are DETERMINISTIC HOST snippets, exactly like discovery.I2C_SCAN_SNIPPET
and bringup/harness.py: the LLM never writes the OLED code. MicroPython ships
`framebuf` but NOT an SSD1306 class, so a compact one is embedded here and
exec'd over the raw REPL (no flash writes — same statelessness as everything
else on this wire).

Two payloads, split so steady-state frames stay tiny:
  * build_init_payload(...) — defines the class + builds the module global
    `_oled`, once per connect. Re-sent by the narrator only when a draw comes
    back with a `NameError` (a soft_reset — e.g. the commission's recovery —
    wipes interpreter globals, so `_oled` vanishes; the board's own error is
    the re-init trigger, in the codebase's react-to-verbatim-error spirit).
  * draw_payload(lines, ...) — ~100-200 B: fill, one text() per row, show().

The built-in FrameBuffer font is 8x8 => 16 chars wide, 8 rows tall on 128x64.
"""

from __future__ import annotations

# The SSD1306 128x64 init sequence (canonical MicroPython/Adafruit order),
# command bytes only. Each is written as [0x80, cmd] (Co=1, D/C=0); pixel data
# is written as b'\x40' + buffer. Horizontal addressing so show() is one blit.
_INIT_CMDS = (
    0xAE,  # display off
    0x20, 0x00,  # memory addressing mode = horizontal
    0x40,  # display start line = 0
    0xA1,  # segment remap (col 127 -> SEG0)
    0xA8, 0x3F,  # multiplex ratio = height-1 (63)
    0xC8,  # COM output scan direction remapped
    0xD3, 0x00,  # display offset = 0
    0xDA, 0x12,  # COM pins config (0x12 for 128x64)
    0xD5, 0x80,  # display clock divide
    0xD9, 0xF1,  # pre-charge period
    0xDB, 0x30,  # VCOMH deselect level
    0x81, 0xFF,  # contrast = max
    0xA4,  # entire display follows RAM
    0xA6,  # normal (non-inverted)
    0x8D, 0x14,  # charge pump on
    0xAF,  # display on
)

_ROW_H = 8  # built-in FrameBuffer font cell height
MAX_COLS = 16  # 128 / 8
MAX_ROWS = 8  # 64 / 8


def build_init_payload(sda: int, scl: int, addr: int, width: int = 128, height: int = 64) -> str:
    """MicroPython source that defines a minimal SSD1306 and builds `_oled`.

    Idempotent to re-send: redefining the class + rebinding `_oled` is safe.
    Ends by clearing the panel so a fresh connect wipes the factory demo frame.
    """
    cmd_list = ",".join(str(c) for c in _INIT_CMDS)
    return (
        "import framebuf\n"
        "from machine import Pin, I2C\n"
        "class _OLED(framebuf.FrameBuffer):\n"
        f"    def __init__(self):\n"
        f"        self.i2c = I2C(0, sda=Pin({sda}), scl=Pin({scl}))\n"
        f"        self.addr = {addr}\n"
        f"        self.w = {width}\n"
        f"        self.pages = {height} // 8\n"
        f"        self.buf = bytearray(self.pages * self.w)\n"
        f"        super().__init__(self.buf, self.w, {height}, framebuf.MONO_VLSB)\n"
        f"        for c in ({cmd_list},):\n"
        "            self.i2c.writeto(self.addr, bytes([0x80, c]))\n"
        "        self.fill(0)\n"
        "        self.show()\n"
        "    def show(self):\n"
        "        for c in (0x21, 0, self.w - 1, 0x22, 0, self.pages - 1):\n"
        "            self.i2c.writeto(self.addr, bytes([0x80, c]))\n"
        "        self.i2c.writeto(self.addr, b'\\x40' + self.buf)\n"
        "_oled = _OLED()\n"
    )


def _ascii(s: str) -> str:
    """The built-in font is ASCII-only; drop the rest so a stray glyph can't
    poison the exec. Also the console uses '//' and '·' — normalize the dot."""
    s = s.replace("·", "-").replace("//", "|")
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in s)


def draw_payload(lines: list[str], *, invert_header: bool = False) -> str:
    """A tiny frame: clear, place each line, blit. Assumes `_oled` exists.

    invert_header=True paints row 0 as a filled bar with black text — the
    active-agent banner. Lines are clipped to 16 cols; extra rows past what
    fits (8, or 6 under a header) are dropped.
    """
    body = ["_oled.fill(0)"]
    y = 0
    for i, raw in enumerate(lines):
        text = _ascii(raw)[:MAX_COLS]
        if invert_header and i == 0:
            body.append("_oled.fill_rect(0, 0, 128, 9, 1)")
            body.append(f"_oled.text({text!r}, 0, 1, 0)")
            y = 12
            continue
        if y > 64 - _ROW_H:
            break
        body.append(f"_oled.text({text!r}, 0, {y})")
        y += _ROW_H if not (invert_header and i == 1) else _ROW_H + 1
    body.append("_oled.show()")
    return "\n".join(body)


def is_uninitialized_error(stderr: str) -> bool:
    """True when a draw failed because `_oled` doesn't exist (fresh boot or a
    soft_reset wiped globals). The signal to re-send build_init_payload()."""
    return "NameError" in stderr and "_oled" in stderr
