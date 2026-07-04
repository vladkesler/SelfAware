# Hardware bring-up: the self-repairing driver loop

## Protocol classes — HOW the MCU reads a device names the driver skeleton

| Class | Mechanism | Driver shape | PicoBricks examples |
|---|---|---|---|
| `analog` | one ADC read | ~one line | LDR (GP27), potentiometer (GP26) |
| `digital_bus` | I2C/SPI conversation | structured exchange | SHTC3 temp/humidity @0x70, SSD1306 OLED @0x3C |
| `pulse_timing` | `time_pulse_us` choreography | timed dance | HC-SR04 ultrasonic |
| `output` | drive PWM/GPIO, verify cross-modally | non-blocking `set(level)` | buzzer (GP20), relay (GP12) |

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
| SSD1306 OLED | I2C 0x3C | on-board display — "device narrates itself" option |
| SHTC3 | I2C 0x70 | UNCONFIRMED on some revisions |
| Motor driver | GP21/GP22 | revision-dependent; some revisions via I2C 0x22 |
| IR | GP0 | |

ADC-capable pins: **26, 27, 28** (`SELFAWARE_ADC_CAPABLE_PINS`).
5V rule: the RP2040 is **not 5V-tolerant** — a bare HC-SR04 wants 5V Vcc with
the echo line divided down to 3.3V.

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
