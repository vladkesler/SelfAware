# Demo runbook — the judge-facing five minutes

Rehearse the whole arc offline first: `make demo` (mock board + canned author
+ frontend). Nothing in the flagship path depends on wifi, API keys, or the
venue's power strips. Record a screen capture of one clean run as the
last-resort fallback.

## The beats, in order

1. **Cold open — the landing void.** One line, one looping teaser terminal,
   `> enter the console`. No feature grid, no SaaS chrome.
2. **Hotplug — the device materializes.** Plug the sensor in (or let the mock
   hotplug fire): the device surfaces in the SERIAL scan strip (I2C rescans
   automatically every few seconds — no button to press).
   - I2C module → named ("SHTC3 @0x70", confidence: exact) — real
     auto-detection from the bus scan.
   - Analog module → "something on GP27 — what is it?" (confidence: unknown).
     Say the honesty line out loud: *"a raw voltage physically cannot tell you
     what produced it — so we detect presence, and you teach it once."*
3. **Teach it once.** Name it / click the preset → `cmd.commission`.
4. **The flagship: fail → repair → pass on real silicon.** The hero headline and
   the relay light AUTHOR → BOARD; the AGENT column shows the board's **verbatim**
   error in red and the headline flips to `MEDIC // READING THE ERROR`; the relay's
   repair loop-back draws; attempt 2 passes and the headline goes phosphor
   `LIVE // SIGNAL ACQUIRED` with a live reading. Narrate: *"that traceback came
   from the chip, not the model — it can't be hallucinated, and it steers the fix."*
5. **Liveness, not vibes.** Cover the LDR / wave at the ultrasonic — the scope
   moves. (Mock: `cmd.stimulate`.) *"A plausible number is not a live sensor;
   movement under stimulus is."*
6. **Capability accretion.** In the AGENT column (now the PILOT console): "what's
   the light level?" → PILOT calls `read_ldr` — a tool that did not exist five
   minutes ago — and reports the live value. Ask about a sensor that isn't
   commissioned: it says so instead of inventing a number.
7. **The glass brain (Grafana).** Open the Commission Theater dashboard: the
   trace waterfall of the exact commission the judges just watched —
   generate/validate/deploy/test spans, the failed attempt, token usage.
8. **Close with the honesty floor.** Tractable: analog reads, self-identifying
   bus devices, single-pulse timing. Hard: multi-register state machines,
   bit-banged timing. Impossible: "auto-detect anything." Saying this is what
   makes the rest believable.

## Making the first failure deterministic (never hope for a hallucination)

- **Offline/keyless (always works):** `SELFAWARE_MOCK_BOARD=true
  SELFAWARE_MOCK_AUTHOR=true` — canned author + scripted board traceback.
  Pacing: `SELFAWARE_MOCK_PACE_S` (default 1.5) slows the mock author's
  "thinking" and each scripted exec so the fail → repair → pass arc takes a
  narratable ~8s instead of finishing before anyone can see it (tests run at 0).
- **Real board:** the gate intentionally blocks the "non-ADC pin" trick, so
  use the wrong-platform priming route (ESP32-style steering with the gate's
  `.atten` check relaxed via config for the demo run) so the **board itself**
  raises `AttributeError: 'ADC' object has no attribute 'atten'`. Decide and
  rehearse this on build day; see docs/hardware-bringup.md.
- **Physics variant:** passive buzzer driven with DC → no sound → cross-modal
  verify sees no delta → repair switches to PWM. The error is the world
  declining to change.

## Presenter controls (the console is rigged for you)

- **Prompt chips** above the PILOT input (AGENT column) — click, never type on a
  projector. PILOT chat needs a live model (it is offline in `?mock=1` fixture mode).
- **Busy guard** — every commission/read/set affordance disables while the
  bench is busy; a nervous double-click cannot fire `commission_busy`.
- **Error banner** — `system.error` (model_unavailable, board_offline,
  commission_busy) surfaces in the status strip in red and self-dismisses;
  if you see it, walk the failure ladder calmly.
- **The traceback hold** — the theater freezes on the red for ~2 s before the
  repair visually begins. That pause is yours: *"that came from the chip."*
- **Bus rescan is automatic** — the DiscoveryWatcher re-scans I2C every few
  seconds, so devices appear on their own (the old rail `rescan bus` / per-card
  `nudge` buttons were folded away in the console redesign). For liveness on a real
  board, cover the LDR / breathe on the sensor physically; the `?mock=1` fixture
  self-animates the scope after the script ends. (`cmd.board_scan` / `cmd.stimulate`
  still exist on the wire for a scripted control surface.)
- **Fixture tab** (last-resort): pre-stage `…/app?mock=1&hold=1` — it arms
  but waits for a click/keypress to start; `.` restarts the replay; after the
  script ends the scope keeps breathing with synthetic readings for Q&A.
- **Reset ritual between showings:** Ctrl-C the backend, re-run it, reload the
  page. The registry forgets (clean rail/toolbelt) and the mock
  fail→repair→pass script re-arms — it plays **once per backend process**.
  Run backend and frontend in separate terminals so this takes ~5 s.
- Demo snappiness on real hardware: `SELFAWARE_POLLER_INTERVAL_S=0.25` makes
  the cover-the-LDR scope dive read instantly at distance.

## Failure ladder (when hardware misbehaves under fluorescent lights)

1. Real board + real model (the plan).
2. Real board + `SELFAWARE_MOCK_AUTHOR=true` (USB works, wifi/API doesn't —
   the traceback still comes from real silicon; only the author's prose is
   canned).
3. `make demo` fully mock (nothing works but the laptop).
4. The `?mock=1&hold=1` fixture tab (no backend at all).
5. The screen recording (nothing works at all).

Pre-demo checklist: `make infra-up` early (image pulls are slow on venue
wifi); `make test`; one full mock run; one full real run; disable the IDE's
MicroPython auto-connect (it steals the serial port — "device busy" is almost
always this); charge the laptop; macOS Do Not Disturb ON; stand 3 m back once
and confirm the traceback and the hero reading are legible.
