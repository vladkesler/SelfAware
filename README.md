# SelfAware

**Verified hands for AI agents in the physical world.** Plug in a device
nobody wrote a driver for — an AI agent writes the MicroPython driver,
deploys it to a real Raspberry Pi Pico W over USB serial, test-reads it on
real silicon, and **repairs itself from the board's own traceback**. Only
when the hardware itself vouches for the result is the driver admitted to
the registry — where it instantly becomes a live tool (`read_ldr`,
`set_relay`) that an agent copilot can call.

> Reliability is a property of the **loop**, not the model. Every attempt is
> judged by physical hardware; a traceback from the chip cannot be
> hallucinated, and it steers the next fix.

## The missing layer: agents got tools, hardware got left behind

MCP made "agents calling tools" the default way software gets used, and it is
already reaching devices — MCP-to-microcontroller bridges exist today. But
every one of them shares the same hidden assumption: **a human already wrote
and vouched for the driver.** The agent only gets to call adapters a firmware
engineer hand-built, one device at a time. That's a *transport* layer.

What's missing is the **admission layer**: how does a device the system has
*never seen* become callable — and trustworthy — without a human writing
code? SelfAware is that layer. Trust isn't inherited from a human author; it
is **manufactured by the loop**:

1. The agent writes the driver — and is never trusted by default.
2. A host-owned AST safety gate constrains what the code may do before it
   ever touches a pin.
3. Real silicon executes it; the verbatim traceback steers each repair.
4. Physics-based lie detection (railed/floating pin fingerprints, plausible
   range, liveness — the value must *move* when you cover the LDR) rejects
   numbers that merely look right.
5. Only then is the driver admitted to the registry and exposed as a live,
   hot-swappable agent tool.

The human's role shrinks to the one thing only a human can know — "this wire
is an LDR on GP27" — stated once. Everything after that is the loop's
problem. Others distribute trust; SelfAware manufactures it.

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        L["Landing /"] --> C["Console /app<br/>agent theater"]
    end
    subgraph Backend[FastAPI backend]
        WS["/ws<br/>one WebSocket"] --> CMD["CommandRouter<br/>cmd.* → ack → task"]
        BUS["EventBus<br/>global seq, fan-out"] --> WS
        CMD --> SVC["CommissionService<br/>single-flight"]
        SVC --> LOOP["CommissionRunner<br/>bounded self-repair loop"]
        AUTH["driver_author agent<br/>(PydanticAI)"] -. "DriverGenOutput<br/>flat, reasoning first" .-> LOOP
        LOOP --> GATE["AST safety gate<br/>host-owned"]
        LOOP --> BUS
        LOOP --> SESS["BoardSession<br/>THE asyncio.Lock"]
        LOOP <--> REG["DriverRegistry<br/>admission-gated"]
        COP["copilot agent<br/>read_* / set_* tools"] --> SESS
        OTEL["observability<br/>logfire spans"]
        MEMC["memory client<br/>no-op degradable"]
    end
    subgraph Board[Pico W · PicoBricks]
        REPL["raw REPL<br/>exec, no flash writes"] --> GPIO["GPIO · ADC · I2C · pulse"]
    end
    C <-->|"typed JSON events"| WS
    SESS <-->|"USB serial<br/>DTR/RTS suppressed"| REPL
    OTEL -->|"OTLP :4318"| LGTM["grafana/otel-lgtm<br/>Tempo · Loki · Grafana :3000"]
    MEMC -->|"REST :8100"| MEM["agent-memory-server<br/>+ redis"]
```

## The self-repair loop — where trust is manufactured

```mermaid
sequenceDiagram
    participant U as UI (theater)
    participant H as Host (loop.py)
    participant A as LLM (driver_author)
    participant B as Pico W (raw REPL)
    U->>H: cmd.commission {slug, protocol_class, pins}
    loop ≤ max_attempts (default 4)
        H->>A: spec (+ VERBATIM last error, if any)
        A-->>H: reasoning + driver_code (flat schema)
        H->>H: AST safety gate (imports, no while, no flash,<br/>no ESP32-isms, ADC pins, lie-detector)
        alt gate rejects
            H-->>U: commission.stage validate=failed
            Note over H,A: gate reason becomes the next "error"
        else deploy + test
            H->>B: exec driver + host-authored read call
            B-->>H: stdout (last line = reading) / stderr (VERBATIM traceback)
            alt traceback or implausible or timeout
                H-->>U: commission.traceback (verbatim, red)
                Note over H,B: timeout ⇒ soft reset, clean line
            else plausible reading
                H->>H: registry.register (admission gate)
                H-->>U: commission.passed + driver.registered<br/>copilot gains read_slug tool
            end
        end
    end
    H-->>U: commission.failed (honest, with last traceback)
```

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, and — only for the
observability/memory stack — [Docker](https://docs.docker.com/get-docker/)
with the daemon running (Docker Desktop or Colima on macOS). No hardware and
no API key needed for the full mock demo.

```bash
# one-time setup
cd backend && uv sync --group dev && cd ..
cd frontend && npm install && cd ..

# 0. nothing required: no hardware, no API key, no docker
make test        # backend suite — green offline by design

# 1. the full theater, zero dependencies (MockBoard + canned author)
make demo        # backend :8000 (mock) + frontend :5173
#    open http://localhost:5173  →  "> enter the console"
#    or fixtures-only, no backend at all: http://localhost:5173/app?mock=1

# 2. observability + memory (optional; needs the Docker daemon running)
make infra-up    # docker compose: grafana/otel-lgtm (Grafana :3000, OTLP
                 #   :4317/:4318) + agent-memory-server :8100 + redis :6379;
                 #   first run pulls ~1.5 GB of images — start it early.
                 # the SelfAware · Commission Theater dashboard auto-provisions;
                 # backend traces appear under service "selfaware-backend"
make infra-down  # stop the stack (add -v in infra/ to also drop redis data)

# 3. real everything (each switch independent — see degradation matrix)
cp .env.example .env             # pick a model + set its key (see "Model provider")
make dev-backend                 # plug in the Pico W first; port auto-discovered
make dev-frontend
```

The backend never *requires* the containers: if the stack is down, traces are
dropped silently and memory degrades to a no-op client.

### Model provider

`SELFAWARE_MODEL` is the one switch — any PydanticAI `provider:model` string,
with the matching key in `.env`. Anthropic is the default; **Crusoe** (an
OpenAI-compatible inference endpoint) is wired in under a `crusoe:` prefix:

```bash
SELFAWARE_MODEL=crusoe:moonshotai/Kimi-K2.6
CRUSOE_API_KEY=your-crusoe-key
# SELFAWARE_CRUSOE_BASE_URL=https://api.inference.crusoecloud.com/v1/   # override for a proxy/region
```

Scope Crusoe to just the driver author with `SELFAWARE_AUTHOR_MODEL=crusoe:…`
and leave the copilot on another provider. A missing key fails fast with a
clean `model_unavailable` error — never mid-commission.

| | |
|---|---|
| Dashboard | http://localhost:5173/app |
| Backend health | http://localhost:8000/healthz |
| Grafana (agent traces) | http://localhost:3000 → *SelfAware · Commission Theater* |

## Degradation matrix — everything is optional

| Missing | What still works |
|---|---|
| API key | Everything except real codegen; `SELFAWARE_MOCK_AUTHOR=true` runs the full loop keyless |
| Board | Everything via `SELFAWARE_MOCK_BOARD=true` (explicit — absence of a board is reported honestly, never silently mocked) |
| redis / agent-memory | Everything; memory degrades to a no-op client |
| Grafana LGTM | Everything; OTLP exporter is fail-open |
| **all of the above** | `make test` and `make demo` — the flagship demo has zero external dependencies |

## Repo map

```
backend/selfaware/
  events/         the typed wire language (docs/event-protocol.md is canonical)
  hardware/       raw-REPL bridge, MockBoard, discovery, THE single lock
  bringup/        the bounded loop: gate → deploy → test → repair
  agents/         driver_author + copilot (PydanticAI), streaming bridge
  registry/       verified drivers → live hot-swappable tools
  memory/         agent-memory-server client (no-op degradable) + sqlite-vec stub
  observability/  logfire → OTLP → local Grafana
  api/            create_app factory, /ws, REST, lifespan
frontend/src/     the agent theater (see docs/frontend.md)
infra/            docker-compose (redis, agent-memory, otel-lgtm) + dashboards
docs/             architecture · event-protocol · backend · frontend · agents ·
                  hardware-bringup · observability · demo-runbook
```

## The honesty floor (read before demoing)

- **Tractable:** analog reads, self-identifying I2C devices, single-pulse
  timing — these converge in a few attempts.
- **Harder (don't overclaim):** multi-register state machines, strict
  bit-banged timing (WS2812, quadrature).
- **Physically impossible (never claim):** "auto-detect anything attached."
  A raw voltage cannot reveal what produced it. We auto-identify I2C devices
  (they announce themselves), detect *presence* on ADC pins, and let the human
  teach the rest — once.
- **A plausible number is not a live sensor.** The host checks range *and*
  fingerprints (railed/floating pins), and real liveness means the value
  moves when you cover the LDR.

Docs: [architecture](docs/architecture.md) · [event protocol](docs/event-protocol.md) ·
[hardware bringup](docs/hardware-bringup.md) · [agents](docs/agents.md) ·
[frontend](docs/frontend.md) · [backend](docs/backend.md) ·
[observability](docs/observability.md) · [demo runbook](docs/demo-runbook.md)
