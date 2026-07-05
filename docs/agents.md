# Agents (PydanticAI)

Two LLM roles, both module-level singletons constructed **without a model** —
the model string is resolved per run from `Settings` (`SELFAWARE_MODEL`, one
switch, any `provider:model` string; `SELFAWARE_AUTHOR_MODEL` optionally
overrides for the author). Importing `selfaware.agents` never touches
credentials; a missing key surfaces at run time as
`system.error{model_unavailable}`, never at boot.

## driver_author (`agents/author.py`)

The codegen half of the loop. Deliberately minimal:

- **No tools.** The author never touches the board — the host deploys and
  tests (host/LLM split). One model request per attempt.
- **No message_history.** Repair context is rebuilt each attempt from
  `AttemptContext{attempt_n, previous_code, failure_kind, verbatim_error}` —
  the host controls exactly what the model sees, and the loop is replayable.
- **Output:** `DriverGenOutput` — FLAT, three fields, order load-bearing:
  `reasoning` (think first) → `driver_code` → `imports_used` (cross-checked
  against the AST by the gate: a cheap lie detector).
- **Dynamic instructions** inject the per-class fragment
  (`agents/prompts/protocol_classes/<class>.md`) + board constraints, so the
  same landmines are both *steered around* (prompt) and *caught* (gate).
- The repair template embeds the traceback **verbatim** under a
  "the board replied:" header.

`mock_author.py` provides a drop-in canned author
(`SELFAWARE_MOCK_AUTHOR=true`): a scripted fail→repair→pass sequence paired
with the MockBoard demo script — the flagship demo cannot be killed by a
missing key.

## copilot (`agents/copilot.py`)

The dashboard's voice. `output_type=str`, streamed.

- **Static tools:** `commission_sensor` (enqueues via `CommissionService`,
  returns immediately — a 4-attempt hardware loop never sits inside a chat
  turn), `list_devices`, `board_status`, `recall` (answers "memory offline"
  honestly when degraded).
- **Dynamic tools:** `read_<slug>` / `set_<slug>` built from the live registry
  each run; each tool re-resolves `registry.get(slug)` **at call time**, so a
  repair hot-swaps the implementation mid-conversation.
- **Honesty floor in the instructions:** report only what tools return; if a
  sense isn't commissioned, say so — never invent a reading. The model is a
  reporter of sensors, never their oracle.

## Streaming bridge (`agents/streaming.py`)

`run_agent_streaming()` forwards PydanticAI run events onto the EventBus as
canonical `agent.*` payloads (text deltas → `agent.message{delta, done}`,
thinking → `agent.thought`, tool calls/results → `agent.tool_call/_result`,
final usage on the closing frame). The event-class mapping lives in a pure
`_forward()` function, unit-tested without a model. Chat history is kept
per-connection and passed as `message_history`.

## Testing

`ALLOW_MODEL_REQUESTS=False` globally in conftest — any accidental real call
fails loudly. `TestModel` proves schemas/instructions render keyless;
`FunctionModel`/callable authors drive the full commission-loop test
(gate-reject → board-traceback → pass) against the scripted MockBoard.

## MCP transport (`mcp_server.py`) — external agents, not just the copilot

The copilot is one, first-party consumer of `read_<slug>`/`set_<slug>`. MCP
is how *any* agent — Claude Code, a different vendor's agent, a script —
gets the same capability, without being written into this codebase. Three
design decisions worth knowing before touching this:

- **A SEPARATE process, not mounted into `create_app()`.** Mounting a
  Streamable HTTP MCP server inside an existing ASGI app is a documented,
  currently-unresolved limitation of the MCP Python SDK (redirect loops,
  "Task group is not initialized" — see
  `modelcontextprotocol/python-sdk#1367`). `mcp_server.py` runs standalone
  (`mcp.run_async(transport="http", ...)`, the SDK's own supported mode) and
  talks to the main backend over the network instead of touching
  `BoardSession`/`DriverRegistry` directly — which also means it can never
  violate the single-lock invariant (`hardware/session.py`); it's just
  another caller on the existing REST surface, same as the frontend.
- **Stateless by construction.** `RegistryProvider._list_tools()` resolves
  the tool list against `GET /api/drivers` on **every MCP request** — the
  same resolve-at-call-time invariant as the copilot's dynamic toolset
  above, at one loopback GET per request. There is no mirror, no event
  listener, and no reconciliation pass, because there is no local tool
  state that could drift: a re-commission, a repair that flips a slug
  between read and set, or a demotion out of ACTIVE is simply reflected in
  the next request's answer. Tool *calls* resolve through the same path, so
  a de-commissioned driver's tool call fails with a clean not-found rather
  than running against a stale record.
- **Bearer-token gated, fails closed.** Every endpoint that can touch real
  hardware from outside the process (`POST /api/drivers/{slug}/read`, `/set`,
  `/api/board/scan`, `/api/commission`, `/api/oled/say` — `api/rest.py`) is
  guarded. `SELFAWARE_MCP_TOKEN` unset means those endpoints refuse every
  request (403) — never "open to anyone," the same honest-degrade posture as
  everything else here, just at a boundary where the failure mode is real
  actuation instead of a blank dashboard widget.
  One more boundary, stated plainly: the MCP port itself (:8001) carries no
  auth — the loopback-only default bind (`SELFAWARE_MCP_HOST=127.0.0.1`) is
  its only guard. Don't bind it wider without adding client auth.

Alongside the dynamic per-driver tools, a **static** surface exists from t=0
(before anything is commissioned), covering the whole bench lifecycle:

- **Discover** — `list_capabilities` (board status + every driver and the
  tool that drives it), `probe_bus` (a live I2C scan; matches against the
  known-device table carry a `preset_slug`), and
  `list_commissionable_devices` (the preset catalog, annotated with
  what's already commissioned).
- **Commission** — `commission_device(preset_slug)` starts the full
  AUTHOR→MEDIC self-repair loop and polls the backend inside the call for up
  to ~45 s (`SELFAWARE_MCP_COMMISSION_WAIT_S`); a slower real run returns an
  honest `status: "running"` + `commission_id` for `get_commission_status`.
  The REST seam is 202-then-poll (`POST /api/commission` →
  `GET /api/commission/{id}`) because a commission outlives any sane HTTP or
  MCP-client timeout, and `CommissionService` keeps a small ring of terminal
  outcomes (passed/failed/**crashed**, with the verbatim per-attempt record)
  so a caller who timed out and lost its request can still learn what
  happened. An MCP-initiated commission publishes the same `commission.*`
  events as any other — the web console animates it for free.
- **Operate** — `read_sensor(slug)` / `set_actuator(slug, level)` gateways
  to the same token-gated seams, `get_sensor_health(slug)` (the same verdict
  the `sensor.health` event carries), `get_sensor_history(slug)` (the
  sparkline's points), `get_driver_code(slug)` (the silicon-verified source
  with provenance — the registry stores exactly the text that passed), and
  `display_message(text)` (a short message on the physical OLED, honest 409
  when no display is present).

The gateways matter because fastmcp only pushes `tools/list_changed` from
inside an active request context — a sensor commissioned while an external
session is open will NOT appear in that session's tool list until the client
re-lists (Claude Code: `/mcp` → reconnect). `list_capabilities` →
`read_sensor("<slug>")` / `set_actuator("<slug>", …)` covers that gap with
no reconnect at all.

Honesty floor for callers we don't own: an external agent's system prompt is
outside our control, so the guardrail travels with the data instead —
every tool description and every response payload states the reading is
live, taken at call time, not cached.

Run it: set `SELFAWARE_MCP_TOKEN` once in `.env`, then `make dev-backend` +
`make dev-mcp` (the Makefile exports `.env` to both; start order doesn't
matter). Claude Code picks the server up from the repo's checked-in
`.mcp.json` (`http://127.0.0.1:8001/mcp`) — run `claude` from the repo root
and approve the project server once. From elsewhere:
`claude mcp add --transport http selfaware http://127.0.0.1:8001/mcp`.
