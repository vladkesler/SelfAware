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
8. **An agent that isn't ours, over MCP.** Switch windows entirely to Claude
   Desktop (a separate process, connected via MCP — see setup below), open a
   **fresh** conversation, and ask "what's the light level right now?" It
   discovers `read_ldr` on its own and reports the live value — proof that a
   process you don't control just used the hardware. Cover the sensor, ask
   again, show the value change: liveness, but witnessed by an agent that
   isn't SelfAware's own UI. Narrate: *"MCP is the difference between 'our
   chatbot can read a sensor' and 'any agent can gain a verified physical
   capability' — that's the admission layer, not the transport layer."*
9. **Close with the honesty floor.** Tractable: analog reads, self-identifying
   bus devices, single-pulse timing. Hard: multi-register state machines,
   bit-banged timing. Impossible: "auto-detect anything." Saying this is what
   makes the rest believable.

## Setting up the MCP beat (do this before judges arrive, not during)

1. Set the **same** `SELFAWARE_MCP_TOKEN` in `.env` (read by the main
   backend) — `mcp_server.py` reads it from its own process environment, so
   export it in the shell you launch `make dev-mcp` from too.
2. `make dev-backend` (or `make demo-mock` for the keyless path), then
   `make dev-mcp` in a second terminal — two processes, on purpose (see
   `docs/agents.md`: mounting MCP into the main app hits a documented SDK
   bug).
3. Add the server to Claude Desktop's config (`claude_desktop_config.json`),
   pointing at `http://127.0.0.1:8001/mcp`, and restart Claude Desktop so it
   picks up the connection.
4. **Verify before judges see it, don't hope:** commission a sensor first,
   then confirm Claude Desktop actually lists `read_<slug>` as an available
   tool. Whether an already-open conversation picks up a *newly* commissioned
   sensor without restarting is untested against Claude Desktop specifically
   — rehearse that exact moment once, and if it doesn't push live, "ask in a
   new conversation" is the rehearsed fallback, decided in advance, not
   improvised on stage.
5. Keep this beat sequenced, not interleaved with beat 4's `make demo-mock`
   rehearsal: MockBoard's scripted fail→pass exchanges are consumed in
   strict order, and a stray MCP-triggered read mid-rehearsal will desync
   the script.

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
