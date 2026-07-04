# Architecture

```
Browser (React) ──WebSocket──► FastAPI backend ──USB serial──► Pico W ──GPIO──► sensor
 "agent theater"    (network)   raw-REPL bridge   (electrical)
```

SelfAware is the admission layer between AI agents and physical hardware:
plug in a device nobody wrote a driver for, teach it once, and an AI agent
writes the MicroPython driver, deploys it over USB serial, test-reads it on
real silicon, and self-repairs from the board's own traceback. A driver that
survives the loop is admitted to the registry and becomes a live tool an
agent can call — trust is manufactured by the loop, not inherited from a
human author.

## The one loop everything serves

```
generate ──► static AST gate ──► deploy (raw-REPL exec, NO flash writes) ──► test-read
   ▲                                                                            │
   └────────────── verbatim traceback fed back (≤ max_attempts) ◄───────────────┘
```

Bounded (default 4 attempts), then soft reset + an **honest FAILED**. Success
is never "code compiles" — it's *a plausible value came back from the metal*.

## Host / LLM split (the reliability story)

| Responsibility | Owner | Where |
|---|---|---|
| Safety gate (AST allowlist, no while, no flash, no ESP32-isms) | Host | `bringup/gate.py` |
| Retry budget, timeouts, soft reset | Host | `bringup/loop.py`, `hardware/session.py` |
| Serial ownership, raw-REPL framing, THE lock | Host | `hardware/` |
| Harness (read/set call appended to driver code) | Host | `bringup/harness.py` |
| Plausibility + liveness verdicts | Host | `bringup/plausibility.py` |
| Discovery (I2C scan, ADC signatures) | Host | `hardware/discovery.py`, `watcher.py` |
| **Writing the driver body** | **LLM** | `agents/author.py` |
| **Proposing a fix from a traceback** | **LLM** | `agents/author.py` (repair prompt) |
| Chat / operating commissioned hardware | LLM (via host-owned tools) | `agents/copilot.py` |

An LLM that is occasionally wrong is fine inside a host that is never wrong
about safety, identity, and termination. **Reliability is a property of the
loop, not the model.**

## The single-lock rule

Exactly one `asyncio.Lock`, inside `hardware/session.py::BoardSession`.
The telemetry poller, discovery watcher, chat tool calls, and commissions all
share one wire; every exec goes through the session. Nothing outside
`hardware/` ever holds the raw transport. Exclusive operations (commissions)
use the pause-under-lock pattern: acquire the lock (drains any in-flight
exec), cancel the poller, reap it, work, restart it.

## Data flow

1. Client connects to `/ws` → `system.hello` (full state: board + drivers).
2. Client sends `cmd.*` → `system.ack` → handler runs as a background task.
3. Every subsystem publishes typed events to the in-process `EventBus`
   (`events/bus.py`), which stamps a global monotonic `seq` and fans out to
   per-socket bounded queues (drop-oldest — a slow tab never backpressures the
   loop).
4. The frontend applies each event through one exhaustive switch
   (`state/dispatch.ts`) and stages it through the renderer registry
   (`theater/registry.ts`).

Contract: [`docs/event-protocol.md`](event-protocol.md) — canonical; mirrored
by `backend/selfaware/events/` and `frontend/src/types/events.ts`.

## Capability accretion

A driver enters the registry **only after a real on-board pass** (admission
gate). Registration arms `read_<slug>` / `set_<slug>` tools for the copilot;
tools resolve the driver from the registry **at call time**, so a later repair
hot-swaps the implementation under a stable tool name. The agent's toolbox
grows as hardware is commissioned — every tool is backed by verified silicon.

## Degradation matrix

| Missing | Result |
|---|---|
| API key | Boots; commissions/chat → `system.error{model_unavailable}` — unless `SELFAWARE_MOCK_AUTHOR=true` (canned author: full loop, keyless) |
| Board | Boots; `SELFAWARE_MOCK_BOARD=true` gives the full mock theater; otherwise honest disconnected status — **never a silent mock fallback** |
| redis / agent-memory-server | Boots; NullMemoryClient; `recall` answers "memory offline" |
| Grafana LGTM | Boots; OTLP exporter is fail-open (buffers, then drops) |
| All four | `make test` green; `make demo-mock` runs the whole theater |
