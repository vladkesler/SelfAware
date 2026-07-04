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
is how *any* agent — Claude Desktop, a different vendor's agent, a script —
gets the same capability, without being written into this codebase. Two
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
- **Bearer-token gated, fails closed.** `POST /api/drivers/{slug}/read` and
  `/set` (`api/rest.py`) are the only two endpoints that can touch real
  hardware from outside the process. `SELFAWARE_MCP_TOKEN` unset means those
  endpoints refuse every request (403) — never "open to anyone," the same
  honest-degrade posture as everything else here, just at a boundary where
  the failure mode is real actuation instead of a blank dashboard widget.

Tool lifecycle: `mcp_server.py` seeds from `GET /api/drivers` at startup,
then listens on `/ws` for `driver.registered`/`driver.updated` and
re-fetches `GET /api/drivers/{slug}` on either — one reconciliation path,
not two — because `DriverUpdatedPayload` carries no `protocol_class`, so a
repair that flips a slug between read and set can only be detected by
re-fetching the record, not by trusting the event payload alone. A `slug →
tool_kind` map (`_armed`) is what lets that reconciliation remove a stale
`read_<slug>` and arm `set_<slug>` instead of leaving a broken tool name
behind.

Honesty floor for callers we don't own: an external agent's system prompt is
outside our control, so the guardrail travels with the data instead —
every tool description and every response payload states the reading is
live, taken at call time, not cached.

Run it: `make dev-mcp` (needs `SELFAWARE_MCP_TOKEN` set the same in both
`.env` and wherever the main backend reads it — see `.env.example`).
