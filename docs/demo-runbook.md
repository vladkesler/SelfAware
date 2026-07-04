# Demo runbook — the judge-facing five minutes

Rehearse the whole arc offline first: `make demo` (mock board + canned author
+ frontend). Nothing in the flagship path depends on wifi, API keys, or the
venue's power strips. Record a screen capture of one clean run as the
last-resort fallback.

## The beats, in order

1. **Cold open — the landing void.** One line, one looping teaser terminal,
   `> enter the console`. No feature grid, no SaaS chrome.
2. **Hotplug — the device materializes.** Plug the sensor in (or let the mock
   hotplug fire): a card appears on the DeviceRail.
   - I2C module → named card ("SHTC3 @0x70", confidence: exact) — real
     auto-detection from the bus scan.
   - Analog module → "something on GP27 — what is it?" (confidence: unknown).
     Say the honesty line out loud: *"a raw voltage physically cannot tell you
     what produced it — so we detect presence, and you teach it once."*
3. **Teach it once.** Name it / click the preset → `cmd.commission`.
4. **The flagship: fail → repair → pass on real silicon.** The stepper lights
   generate → validate → deploy → test; the TracebackPane interrupts in red
   with the board's **verbatim** error; the repair loop-back draws; attempt 2
   passes with a live reading. Narrate: *"that traceback came from the chip,
   not the model — it can't be hallucinated, and it steers the fix."*
5. **Liveness, not vibes.** Cover the LDR / wave at the ultrasonic — the scope
   moves. (Mock: `cmd.stimulate`.) *"A plausible number is not a live sensor;
   movement under stimulus is."*
6. **Capability accretion.** Open the ChatDock: "what's the light level?" →
   the copilot calls `read_ldr` — a tool that did not exist five minutes ago —
   and reports the live value. Ask about a sensor that isn't commissioned: it
   says so instead of inventing a number.
7. **The glass brain (Grafana).** Open the Commission Theater dashboard: the
   trace waterfall of the exact commission the judges just watched —
   generate/validate/deploy/test spans, the failed attempt, token usage.
8. **Sensor health, not just a reading.** Open `GET /api/drivers/ldr/health`
   right after commissioning: `status: "unknown"` — say the honesty line out
   loud: *"ten readings, not zero, before we'll claim a health status; a
   guess dressed up as a score is exactly what we refuse to do everywhere
   else."* Wait ~40s for it to settle to `"healthy"`. Then run the
   destabilize trick (see setup below) live — the status flips to
   `"degrading"`/`"critical"` with a **named** reason (a real variance ratio
   or a railed-pin fingerprint), not a bare number, and the trend carries a
   capped, short-horizon ETA instead of a fabricated forecast. Close this
   beat on the actuator case: `GET /api/drivers/buzzer/health` answers
   `"not_monitored"`, not an endless `"unknown"` — *"we say what we can't
   measure, not just what we can."*
9. **Close with the honesty floor.** Tractable: analog reads, self-identifying
   bus devices, single-pulse timing. Hard: multi-register state machines,
   bit-banged timing. Impossible: "auto-detect anything." Saying this is what
   makes the rest believable.

## Setting up the health-score beat (rehearse the timing, don't wing it)

The health/trend calculation (`docs/agents.md` has none of this — see
`backend/selfaware/analytics/health.py`) needs real accumulated readings, so
timing is the whole trick: nothing here is faked, which means nothing here
is instant either.

1. Commission `ldr` (WS `cmd.commission {preset_slug: "ldr"}` — no REST
   equivalent exists). `GET /api/drivers/ldr/health` immediately after should
   read `"unknown"` — that's correct, not a bug to fix before the demo.
2. Let ~40s of real polling pass (`poller_interval_s` default 1.0s) before
   checking again — `MIN_POINTS_FOR_STATUS` is 10 readings,
   `MIN_POINTS_FOR_TREND` is 30. `status` should read `"healthy"`,
   `trend.direction` `"stable"`.
3. **The destabilize trick** — the mock's simulated LDR stream genuinely
   gets erratic here, the score isn't told what to say:
   ```bash
   cd backend && uv run python -c "
   import asyncio, json, websockets

   async def main():
       async with websockets.connect('ws://localhost:8000/ws') as ws:
           await ws.recv()  # hello
           for i in range(12):
               delta = 15000 if i % 2 == 0 else -15000
               await ws.send(json.dumps({'type': 'cmd.stimulate', 'id': f's{i}', 'payload': {'slug': 'ldr', 'delta': delta}}))
               await ws.recv()  # system.ack
               await asyncio.sleep(1.2)

   asyncio.run(main())
   "
   ```
   `GET /api/drivers/ldr/health` afterward should show `"degrading"` or
   `"critical"` with a variance reason. **More deterministic fallback** if
   the alternating-variance version doesn't land cleanly in rehearsal: repeat
   the same loop with a single sustained `delta: 30000` instead of
   alternating — pushes the value toward the observed ceiling every cycle,
   which reliably trips the railing signal (`"critical"`, "railed-pin
   fingerprint" reason) rather than depending on a variance ratio crossing
   the threshold at just the right moment.
4. Commission `buzzer` the same way, then `GET /api/drivers/buzzer/health` —
   expect `"not_monitored"`, confirming an actuator never gets stuck
   claiming "not enough data yet" forever.
5. Don't run this destabilize script during a `make demo-mock` rehearsal of
   beat 4 — it's a separate `cmd.*` traffic pattern hitting the same mock
   board and will desync the scripted fail→pass exchanges if interleaved.

## Making the first failure deterministic (never hope for a hallucination)

- **Offline/keyless (always works):** `SELFAWARE_MOCK_BOARD=true
  SELFAWARE_MOCK_AUTHOR=true` — canned author + scripted board traceback.
- **Real board:** the gate intentionally blocks the "non-ADC pin" trick, so
  use the wrong-platform priming route (ESP32-style steering with the gate's
  `.atten` check relaxed via config for the demo run) so the **board itself**
  raises `AttributeError: 'ADC' object has no attribute 'atten'`. Decide and
  rehearse this on build day; see docs/hardware-bringup.md.
- **Physics variant:** passive buzzer driven with DC → no sound → cross-modal
  verify sees no delta → repair switches to PWM. The error is the world
  declining to change.

## Failure ladder (when hardware misbehaves under fluorescent lights)

1. Real board + real model (the plan).
2. Real board + `SELFAWARE_MOCK_AUTHOR=true` (USB works, wifi/API doesn't).
3. `make demo` fully mock (nothing works but the laptop).
4. The screen recording (nothing works at all).

Pre-demo checklist: `make infra-up` early (image pulls are slow on venue
wifi); `make test`; one full mock run; one full real run; disable the IDE's
MicroPython auto-connect (it steals the serial port — "device busy" is almost
always this); charge the laptop.
