# Frontend — the agent theater

Vite + React + TS + zustand. Run: `make dev-frontend` (:5173). A **theater, not a
dashboard**: the backend narrates the loop as typed events; the UI stages them around
a **cast of three real agents**.

## The layout

A slim **fascia** (brand · `COMMISSION ▸` preset picker · link/board dots · `MOCK` ·
senses count · model) / a **HERO band** — the single focal region: a giant phase
headline + the agent **relay** + a live **SIGNAL** reading card / then three calm work
columns: **DRIVER** (the streaming code), **AGENT** (the active agent's mind + the tools
it is calling), **SERIAL** (a milestone-only strip). `theater/agents.ts derivePhase()`
is the single source of "who is on stage" — the headline and the relay both read it, so
they can never disagree.

## The cast (three REAL agents + honest participants)

- **AUTHOR** — writes the driver (the `generate` stage).
- **MEDIC** — reads the board's *verbatim traceback* and rewrites (the `repair` stage).
  AUTHOR and MEDIC are the same `driver_author` LLM in two genuinely different modes.
- **PILOT** — the `copilot`; operates admitted drivers as tools (read / decide / drive).
- **HOST · SCAN / VERIFY** (deterministic discovery + gate + plausibility) and **THE
  BOARD** (real silicon, the arbiter) appear in the relay but are **not** agents.

Every active agent shows the tools it calls as live `ToolChip`s (AUTHOR/MEDIC → `dry_gate`,
PILOT → `read_<slug>` / `set_<slug>`).

## The seams (change these together)

- `state/dispatch.ts` — THE exhaustive switch (a `never` check makes a new event type a
  compile error) mapping events → slice mutations. AUTHOR/MEDIC thoughts + tool calls
  route into the commission trail; PILOT into the chat ledger — keyed on
  `types/events.ts normalizeAgent` (which also folds legacy `driver_author`→author,
  `copilot`→pilot).
- `theater/registry.ts` — pulse-only: event type → which panel's chrome flashes. Feed
  rendering lives in `SerialLog` + `narrate.ts`; unknown event types are never dropped.

## Structure

| Dir | Contents |
|---|---|
| `types/` | `events.ts` (contract mirror — see docs/event-protocol.md; incl. `AgentId` + `normalizeAgent`), `domain.ts` |
| `lib/` | `ws.ts` (reconnect + backoff), `transport.ts` (ws \| fixture), `fixturePlayer.ts`, `parse.ts`, `ring.ts`, `syntax.ts` (MicroPython tokenizer), `presets.ts` |
| `state/` | zustand store + slices: connection, board, commission (trail of `StageRecord`s incl. repair loop-backs; per-attempt code / thoughts / **tools** / traceback), feed (ring 500), drivers (+ discovery presences), readings (ring 512/slug + version counters), chat |
| `theater/` | `agents.ts` (cast + relay + `derivePhase`), `HeroBand`, `AgentRelay`, `AgentColumn`, `AgentRun`, `PilotConsole`, `SourcePane` + `acts/CodeAct`, `SerialLog`, `actors.ts`, `narrate.ts`, `registry.ts`, `pulse.ts` |
| `components/` | primitives (`Panel`, `StatusDot`, `MachineText`, `Sparkline`, `ToolChip`) + panels (`BoardStatus` = the fascia, `ReadingScope` = the scope) |
| `routes/` | `Landing` (pitch + teaser loop), `Console` (fascia / hero band / 3 columns) |
| `fixtures/` | `commission-ldr.json` (canonical demo: scan → AUTHOR writes + `dry_gate` → BOARD traceback → MEDIC repairs → verify → admit → PILOT `read_ldr`), `teaser.json` |
| `styles/` | `tokens.css` (ALL design tokens), `base.css`, `console.css` (layout + fascia + hero + relay + columns), `theater.css` (code well, scope, run beats) |

## Mock mode

`/app?mock=1` (or `VITE_MOCK=1`) swaps the WebSocket for a `FixturePlayer` replaying
`commission-ldr.json` — the full fail→repair→pass **relay** with AUTHOR/MEDIC `dry_gate`
tool calls and a PILOT `read_ldr` beat, zero backend. **If the backend can emit the
fixture's exact sequence, the whole UI works** — that's the contract test. (PILOT chat is
offline in fixture mode; it needs a real model.)

## Performance rule

`sensor.reading` events go into per-slug ring buffers with a version counter;
`ReadingScope` draws via `requestAnimationFrame` + zustand transient `subscribe` — **no
React re-render per sample**. Keep it that way.

## Design direction

Dark instrument in a quiet room. Three surface steps, hairlines not shadows, ONE phosphor
accent (`--phosphor`), `--alert` red RESERVED for verbatim tracebacks/failures, machine
voice (mono) vs UI voice (humanist). **One focal point per view:** the giant phase
headline + the lit agent win; code, logs, and devices are demoted supporting detail. Agents
are differentiated by **name + glyph + relay position, never five hues** (that reimports the
"busy" problem). Motion: events arrive as pulses (`--pulse-ms`), the relay's active node and
the repair loop-back animate, tracebacks interrupt without easing, the scope is the only
thing that idles. Banned: white cards, drop shadows, gradient CTAs, KPI tile grids, and the
word "silicon" in UI copy (use "the board").
