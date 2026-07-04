# SelfAware WebSocket Event Protocol — v1

**This document is the canonical contract.** Its executable twins are
`backend/selfaware/events/` (types.py, envelope.py, payloads.py) and
`frontend/src/types/events.ts`. All three are kept in lockstep by hand —
if you change one, change all three in the same commit.

One WebSocket at `/ws` carries everything: agent activity, the commissioning
loop's narration, live sensor readings, discovery, and chat. There is no
second protocol.

## Envelopes

Server → client (**Event**):

```json
{ "v": 1, "type": "commission.stage", "ts": "2026-07-04T12:00:00Z", "seq": 42, "payload": { } }
```

Client → server (**Command**):

```json
{ "type": "cmd.commission", "id": "<uuid>", "payload": { "preset_slug": "ldr" } }
```

### seq semantics (load-bearing)

- `seq` is **global per backend process** and strictly monotonic — stamped by
  the EventBus, the only envelope writer.
- **Gaps are legal.** A slow subscriber's bounded queue drops its *oldest*
  events rather than backpressuring the commission loop. Clients log gaps,
  never treat them as fatal.
- **Reconnect = rehydrate.** `system.hello` restates full state (board status
  + driver list). Clients never replay missed events.

### Command lifecycle

Every dispatched command is answered: `system.ack{cmd_id}` on acceptance, then
the handler runs as a background task; failures surface as
`system.error{cmd_id, code, message}`. A malformed frame or handler crash
never kills the socket.

## Events (server → client)

| Type | Payload | Notes |
|---|---|---|
| `system.hello` | `{server_version, protocol_v, board: BoardStatus, drivers: DriverSummary[]}` | First frame on every connection |
| `system.ack` | `{cmd_id}` | |
| `system.error` | `{code, message, cmd_id?, detail?}` | codes: `unknown_command`, `handler_error`, `model_unavailable`, `board_offline`, `mock_only`, ... |
| `board.connected` | `{port_id, mock}` | |
| `board.disconnected` | `{reason}` | |
| `board.status` | `{connected, port_id, mock, busy}` | `busy` = a commission holds the exclusive lock |
| `commission.started` | `{commission_id, slug, display_name, protocol_class, pins, max_attempts}` | |
| `commission.stage` | `{commission_id, attempt, stage, status, detail}` | `stage ∈ generate\|validate\|deploy\|test\|repair`, `status ∈ started\|passed\|failed` |
| `commission.traceback` | `{commission_id, attempt, stage, traceback}` | **traceback is VERBATIM board stderr** — never trimmed, never re-wrapped |
| `commission.passed` | `{commission_id, slug, attempts_used, reading?, unit}` | |
| `commission.failed` | `{commission_id, slug, attempts_used, reason, last_traceback?}` | honest failure after the attempt budget |
| `agent.thought` | `{agent, text}` | `agent ∈ driver_author\|copilot` |
| `agent.tool_call` | `{agent, tool, args, tool_call_id}` | |
| `agent.tool_result` | `{agent, tool, tool_call_id, ok, preview}` | preview truncated ~500 chars |
| `agent.message` | `{agent, delta, done, usage?}` | streamed chat; client accumulates deltas |
| `sensor.reading` | `{slug, value, unit, plausible}` | `plausible` is the HOST's verdict |
| `actuator.state` | `{slug, level, ok}` | feedback for `cmd.set` |
| `discovery.device_found` | `{bus, addr?, pin?, identity?, confidence, suggested_spec?}` | `bus ∈ i2c\|adc`; `confidence ∈ exact\|unknown` — see honesty note below |
| `discovery.device_lost` | `{bus, addr?, pin?}` | |
| `driver.registered` | `{slug, display_name, protocol_class, pins, tool_names, code_hash, unit}` | flat; emitted ONLY after a real on-board pass |
| `driver.updated` | `{slug, code_hash, reason}` | `reason ∈ repair\|recommission`; tools hot-swap |
| `ui.panel` | `{hint, target}` | `hint ∈ focus\|pulse`, `target` is a PanelId |

`ProtocolClass = analog | digital_bus | pulse_timing | output` — the same
strings appear in payloads, TS types, and `agents/prompts/protocol_classes/*.md`
filenames.

## Commands (client → server)

| Type | Payload | Notes |
|---|---|---|
| `cmd.commission` | `{preset_slug}` **or** full spec fields (`slug, display_name, protocol_class, pins: {role: gpio}, i2c_addr?, expected_min?, expected_max?, unit?, stimulus_hint?, verify_with_slug?, extra_context?`) | maps 1:1 to `BringupSpec`; single-flight — a second commission while one runs is rejected |
| `cmd.read` | `{slug}` | live read via the registered driver → `sensor.reading` |
| `cmd.set` | `{slug, level}` | outputs only → `actuator.state`; guaranteed set(0) path on error |
| `cmd.chat` | `{text}` | copilot agent; streams `agent.*` events |
| `cmd.board_scan` | `{}` | port discovery + I2C scan → `board.status` + `discovery.*` |
| `cmd.stimulate` | `{slug, delta}` | **mock-only** (liveness demo offline); real board → `system.error{code: mock_only}` |

## Discovery honesty (what plug-and-detect can and cannot claim)

- **I2C**: a bus scan deterministically reports responding addresses; a known
  table maps address → identity (`confidence: "exact"`, `suggested_spec`
  pre-filled). This is real auto-detection.
- **ADC**: only *presence change* is detectable (floating pin = noisy
  mid-scale; railed = wrong-pin signature; driven = idles near ½ supply and
  moves). `confidence` is always `"unknown"` — a raw voltage cannot reveal the
  part; the human names it (that's the "teach it once" step).
- **Pulse-timing**: no passive detection; devices only answer a trigger
  choreography.

## Versioning

`PROTOCOL_VERSION = 1` on both sides; `system.hello.protocol_v` is checked at
connect. Unknown event types are **never an error** — clients render them as
raw feed rows, so an out-of-sync backend degrades to "raw but visible."
