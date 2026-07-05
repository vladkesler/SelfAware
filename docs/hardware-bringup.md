# Hardware bring-up: the self-repairing driver loop

## Protocol classes — HOW the MCU reads a device names the driver skeleton

| Class | Mechanism | Driver shape | PicoBricks examples |
|---|---|---|---|
| `analog` | one ADC read | ~one line | LDR (GP27), potentiometer (GP26) |
| `digital_bus` | I2C/SPI conversation | structured exchange | SHTC3 temp/humidity @0x70, SSD1306 OLED @0x3C |
| `pulse_timing` | `time_pulse_us` choreography | timed dance | HC-SR04 ultrasonic |
| `output` | drive PWM/GPIO **or an I2C actuator**, verify cross-modally | non-blocking `set(level)` | buzzer (GP20), relay (GP12), servo (S1–S4 via I2C 0x22) |

The `BringupSpec` handed to the LLM names the class **explicitly** — the model
never guesses the mechanism.

## The loop, stage by stage (`bringup/loop.py`)

1. **generate** — the author agent fills `DriverGenOutput` (flat, 3 fields,
   `reasoning` before `driver_code` so the model thinks before it codes).
2. **validate** — `gate.py` AST checks, host-side, instant: import allowlist
   per class; forbid `open/exec/eval/compile/__import__/input`; forbid
   `reset/deepsleep/bootloader/irq` and the ESP32-only `.atten/.width` (models
   hallucinate these on RP2040 constantly); **no `while` at all** (a while-True
   driver wedges the serial line); `for` bounded by a constant range; ADC pins
   restricted to {26, 27, 28}; `class Driver` shape check; `imports_used`
   lie-detector vs the actual AST.
3. **deploy** — exec-over-raw-REPL of the driver + a **host-authored** harness
   call (`print(Driver().read())`). No flash writes: every attempt is
   stateless, takes effect without reboot, wears nothing.
4. **test** — the last stdout line is the reading; `plausibility.py` judges it
   (host-defined, per class). Non-empty stderr is the **verbatim traceback**.
5. **repair** — the traceback (or gate reason, or timeout note) feeds the next
   attempt **untouched**. Paraphrasing would throw away the one signal that
   cannot be hallucinated.

Budget: `SELFAWARE_MAX_ATTEMPTS` (default 4) → soft reset → honest FAILED.

## Raw-REPL discipline (`hardware/raw_repl.py`, `serial_board.py`)

- Enter: CTRL-C ×2 (kill any boot program) → `\r` + CTRL-A → wait for the
  literal `raw REPL; CTRL-B to exit\r\n>` prompt.
- Exec: code + CTRL-D → `OK` + stdout + EOT(0x04) + stderr + EOT → **consume
  the trailing `>`** or it pollutes the next read.
- stdout/stderr arrive as separate sections — that separation IS the repair
  mechanism (stderr = verbatim traceback; last stdout line = the reading).
- Stateful `RxBuffer`: bytes past a matched marker belong to the next read.
- **DTR/RTS forced low before opening the port** — opening otherwise resets
  the board and the handshake races the reboot (looks like flaky USB; isn't).
- Board addressed by stable id (`/dev/cu.usbmodem*` glob on macOS), never an
  enumerated index.
- Every exec wrapped in a **host** timeout; timeout → dirty-line bit → soft
  reset before the next caller gets the lock.
- Keep prints tiny: REPL stdout silently truncates past a few hundred bytes.

## Plausibility ≠ liveness (the honesty floor)

- A floating ADC pin sits noisy mid-scale; a railed value (≈0 / ≈65535) is the
  "right module, wrong pin" fingerprint — both are **rejected**, not passed.
- `time_pulse_us` returns a **negative sentinel** on timeout — that's "no
  echo", not a distance.
- Outputs can't verify themselves: `output` class uses a cross-modal check
  (an already-commissioned sensor must see the world move), gated on a raw
  delta with **both** a ratio and an absolute margin — the model's units are
  display-only. Day-1 default is soft verify (deploy + set + no traceback),
  stated honestly.
- Real liveness is *movement under stimulus* (`stimulus_hint`: "cover the
  sensor"). `liveness_delta` is the build-day hook.

## PicoBricks pin map (config defaults — env-overridable, revisions differ)

| Module | Pin / addr | Note |
|---|---|---|
| Potentiometer | GP26 (ADC0) | fixed on mainboard |
| LDR | GP27 (ADC1) | fixed on mainboard |
| Button | GP10 | |
| Relay | GP12 | |
| Buzzer | GP20 | passive — needs PWM, not DC (great engineered-repair beat) |
| WS2812 RGB | GP6 | addressable — hard class, not a day-1 target |
| DHT11 | GP11 | **older revisions only**; newer boards ship SHTC3 on I2C |
| I2C0 | SDA GP4 / SCL GP5 | |
| SSD1306 OLED | I2C 0x3C | on-board display — **the device narrates itself**: `hardware/oled_narrator.py` renders the live agentic work (active agent, the self-repair arc, readings + health) over the same host-authored raw-REPL exec path, replacing the factory temp/light demo |
| SHTC3 | I2C 0x70 | **confirmed present** on the bench board (2026-07-04 scan) |
| DC motors M1/M2 | I2C 0x22 | this board: TB6612 behind an I2C co-processor @0x22 (**not** direct GP21/22) |
| Servo S1–S4 | I2C 0x22 | **not GPIOs** — servo channels on the same 0x22 co-processor (see below) |
| IR | GP0 | |

**Bench board, verified 2026-07-04:** Raspberry Pi Pico W / RP2040,
MicroPython v1.27.0, onboard `picobricks.py` + `main.py`.
`I2C(0, sda=GP4, scl=GP5).scan()` → `[0x22, 0x3c, 0x70]`.

ADC-capable pins: **26, 27, 28** (`SELFAWARE_ADC_CAPABLE_PINS`).
5V rule: the RP2040 is **not 5V-tolerant** — a bare HC-SR04 wants 5V Vcc with
the echo line divided down to 3.3V.

## The 0x22 motor/servo co-processor (verified on the bench board)

DC motors **and** servos share ONE I2C command to the co-processor at 0x22 on
`I2C(0, sda=GP4, scl=GP5)` — a 5-byte buffer, command `0x26`, XOR checksum:

    buf = bytearray([0x26, sel, arg2, arg3, sel ^ arg2 ^ arg3])
    i2c.writeto(0x22, buf, False)

- **DC motor (M1/M2):** `sel` = motor number 1–2, `arg2` = speed (PWM byte),
  `arg3` = direction; `speed=0` stops. (This is the `fan` preset.)
- **Servo (S1–S4):** `sel` = `servoNumber + 2` (S1→3 … S4→6), `arg2` = 0,
  `arg3` = angle `0–180`. (This is the `servo` preset.)

Source of truth is the onboard `picobricks.py` (`MotorDriver.servo`); a
gate-clean driver replicates it with raw `machine.I2C` so imports stay
`machine, time` — no library import, exactly like the buzzer/fan presets.

**A servo is still not auto-detectable.** 0x22 announces the *co-processor*
(always present) — it says nothing about whether a servo is plugged into S1.
Identity comes from a human declaring "servo on S1", the "teach it once" step.
Verified live 2026-07-04: `servo(1, angle)` swept the horn 0°→180°→0° on S1,
no traceback (soft verify + eyes).

## Engineering the fail→repair→pass demo (deterministic, not hoped-for)

The gate deliberately blocks the "spec a non-ADC pin" trick (it rejects
`ADC(15)` before the board ever sees it). Deterministic first-failure options:

1. **Offline / keyless**: `SELFAWARE_MOCK_BOARD=true SELFAWARE_MOCK_AUTHOR=true`
   — the canned author calls ESP32's `adc.read()` and the scripted board replies
   with the exact `AttributeError: 'ADC' object has no attribute 'read'` a real
   RP2040 raises, then attempt 2 converges with `read_u16()`. Always
   works; this is the rehearsal and the fallback.
2. **Real board**: prime the author prompt with the wrong-platform convention
   (ESP32-style `.atten()` steering with the gate's `.atten` check temporarily
   relaxed via config) so the **board itself** raises — a board-raised error is
   robust; a hoped-for hallucination is not. Decide and rehearse on build day.
3. **Physics beat**: commission the passive buzzer with DC first — no sound,
   cross-modal verify sees no delta, repair moves to PWM. "The world declining
   to change" as the error signal.
