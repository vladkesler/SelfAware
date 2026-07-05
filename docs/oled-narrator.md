# OLED narrator — the device narrates itself

The onboard SSD1306 (I2C0 @ `0x3C`, SDA GP4 / SCL GP5) stops running the
PicoBricks factory temp/light demo and becomes a live face for the product: the
board narrating its **own** agentic work — which agent is on stage (AUTHOR /
MEDIC / PILOT), the self-repair commission arc as it happens, and live sensor
readings + health at rest.

No new data plumbing. Every fact comes off the same `EventBus` the web console
reads, and the headline strings are ported verbatim from
`frontend/src/theater/agents.ts::derivePhase()`, so **the OLED and the console
can never disagree.**

## Where it lives

| File | Responsibility |
|---|---|
| `hardware/oled_render.py` | Pure, host-authored device code: `build_init_payload()` (embedded minimal `framebuf` SSD1306 → the `_oled` global) and `draw_payload()` (tiny per-frame `fill`/`text`/`show`). |
| `hardware/oled_narrator.py` | `NarratorModel` (bus reducer), pure `agent_lines()` / `telemetry_lines()`, and `OledNarrator` (bus consumer + render loop + the wire). |
| `bringup/loop.py` | `CommissionRunner._draw_oled()` — animates the arc live through the loop's own `ExclusiveBoard` handle. |
| `api/app.py` | Builds the narrator, injects it into the runner, starts it last / stops it first (newest ambience). |
| `config.py` | `oled_enabled`, `oled_refresh_s`, `oled_rotate_s` (+ the existing pin map). |

## How it draws (host-authored, no flash)

Same statelessness as everything else on this wire: the renderer is a
**deterministic HOST snippet** (like `discovery.I2C_SCAN_SNIPPET` and
`bringup/harness.py`) exec'd over the raw REPL. The LLM never writes OLED code.
MicroPython ships `framebuf` but **not** an SSD1306 class, so a compact one is
embedded in `oled_render.py`.

- **Init once.** `build_init_payload()` defines the class and builds a board
  global `_oled`; sent once per connect.
- **Tiny frames.** `draw_payload()` is ~100–200 B — assumes `_oled` exists.
- **Self-heal from the board's own error.** A `soft_reset` (e.g. the commission
  loop's recovery) wipes interpreter globals, so `_oled` vanishes. The next draw
  comes back with a `NameError`; the narrator treats *the board's verbatim
  error* as the re-init trigger (`is_uninitialized_error()`), re-sends the init,
  and redraws. Same react-to-verbatim-error discipline as the repair loop.
- **Absent-display backoff.** If init raises (no display on the bus / wiring
  fault) the narrator marks itself absent and backs off ~30 s instead of
  flooding the wire every tick.

## Two draw paths, one lock

`BoardSession` owns THE single `asyncio.Lock`. A commission holds
`session.exclusive()` end-to-end, so a bus-only narrator would be *blocked* for
the several-second commission — the headline moment. Hence two paths:

- **At rest** — the render loop draws through `session.exec()` (the shared,
  poller-safe lock). It **skips while `board.busy`** (a commission owns the
  wire) and coalesces: a frame hits the wire only when the rendered payload
  actually changed (this also drives the agent↔telemetry rotation without a
  redraw storm).
- **During a commission** — `CommissionRunner._draw_oled()` draws through the
  loop's **own** `ExclusiveBoard` handle at each beat (writing → running →
  traceback → verifying → live), so the self-repair arc animates on the device.
  The stage is passed explicitly (not read off the async model) so it is
  race-free with the event being published, and every call is `try/except`
  wrapped — **a slow, absent, or broken display can never fail, or even slow, a
  commission.**

## What's on screen

128×64 = the built-in 8×8 font gives 16 cols × 8 rows. Row 0 is an inverted
banner (the active agent, or `SELFAWARE` at rest).

- **Agent / commission card** (forced during and briefly after a run): banner
  (`AUTHOR`/`MEDIC`/`PILOT`/`BOARD`/`HOST`), the `derivePhase` headline wrapped,
  `attempt N/M`, and the sub-line. Terminal frames: `LIVE // SIGNAL ACQUIRED`
  (passed) / `NOT ADMITTED` (failed).
- **Telemetry card** (rotates in at rest): board line, then per-sensor
  `SLUG value+unit` with a health chip (`+` healthy · `~` degrading · `!`
  critical).

At rest the two cards rotate every `oled_rotate_s` (default 4 s).

## Degradation (matches the repo's "everything degrades" rule)

- **No board** → the narrator idles; no exec.
- **MockBoard** (`make demo-mock`) → draws are harmless no-ops (an OLED payload
  is neither a `.scan()` nor a sensor-simulator match, so MockBoard returns an
  empty `ExecResult`); the suite stays green with no hardware.
- **`SELFAWARE_OLED_ENABLED=false`** → the narrator never starts; the display is
  left untouched.

## Config

| Setting | Default | Meaning |
|---|---|---|
| `oled_enabled` (`SELFAWARE_OLED_ENABLED`) | `true` | master switch |
| `oled_refresh_s` | `0.5` | render-loop tick; a frame hits the wire only when it changed |
| `oled_rotate_s` | `4.0` | at-rest agent↔telemetry rotation cadence |
| `pins_i2c_sda` / `pins_i2c_scl` / `i2c_addr_oled` | `4` / `5` / `0x3C` | the existing pin map |

## Tests

`backend/tests/test_oled_narrator.py`: `derivePhase` parity for every stage,
`NarratorModel` reduction of the bus events, payload validity (`compile()`,
16-col clip, quote-escaping), end-to-end against MockBoard (init + frame land on
the wire, nothing errors), and the absent-display backoff.
