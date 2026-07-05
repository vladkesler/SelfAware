/**
 * AgentRelay — the cast as a relay. A part travels left→right: the HOST scans
 * the bus, AUTHOR writes a driver, the BOARD (the arbiter) runs it; on a
 * traceback MEDIC repairs and the loop-back sends it back to the board; on a
 * pass the HOST verifies and the driver becomes a live PILOT tool.
 *
 * The three real agents (AUTHOR/MEDIC/PILOT) wear a DiceBear "rings" avatar that
 * SPINS only while that agent is actively working. The BOARD is a square chip
 * mark and the HOST a small checkpoint tick — deliberately NOT rings, because
 * they are not agents: the board is the un-fakeable arbiter, the host is
 * deterministic. Under the lit node hangs the one live caption — what's
 * happening now — plus the agent's own tool chips. Derived entirely from
 * `derivePhase()`, so it can't disagree with the story.
 */

import { RELAY, PERSONAS, type Phase, type StationState } from './agents';
import { ringFor } from './rings';
import { ToolChip } from '../components/primitives/ToolChip';
import type { ActiveCommission } from '../state/slices/commission';

function scarsOf(active: ActiveCommission | undefined): number[] {
  if (!active) return [];
  const failed = new Set<number>();
  for (const r of active.trail) {
    if (r.status === 'failed' && (r.stage === 'test' || r.stage === 'validate')) failed.add(r.attempt);
  }
  return [...failed].sort((a, b) => a - b);
}

export function AgentRelay({
  phase,
  active,
}: {
  phase: Phase;
  active: ActiveCommission | undefined;
}) {
  const scars = scarsOf(active);
  const repairing = phase.activeStation === 'medic' || active?.trail.some((r) => r.stage === 'repair');

  // The live tool chips belong to the agent that is currently on the bench —
  // the author writing / the medic repairing (pilot's hands live in its console).
  const showTools =
    (phase.activeStation === 'author' || phase.activeStation === 'medic') && !!active;
  const tools = showTools ? active!.toolsByAttempt[active!.attempt] ?? [] : [];

  return (
    <div className="relay" data-repairing={repairing ? '' : undefined} data-tone={phase.tone}>
      <div className="relay__track">
        {RELAY.map((station, i) => {
          const state: StationState = phase.stationState[station.id] ?? 'pending';
          const isActive = phase.activeStation === station.id;
          const persona = PERSONAS[station.kind];
          // A ring spins only while its agent is genuinely processing (charge).
          const spinning = isActive && phase.tone === 'charge' && persona.agent;
          const ring = ringFor(persona.key);
          return (
            <div className="relay__cell" key={station.id}>
              {i > 0 ? (
                <span
                  className="relay__link"
                  data-flow={isActive ? '' : undefined}
                  data-done={state === 'passed' || state === 'active' ? '' : undefined}
                />
              ) : (
                <span className="relay__link relay__link--head" />
              )}
              <div
                className="relay__station"
                data-state={state}
                data-active={isActive ? '' : undefined}
                data-agent={persona.agent ? '' : undefined}
                data-kind={persona.key}
              >
                <span className="relay__node">
                  {ring ? (
                    <img
                      className="relay__ring"
                      src={ring}
                      alt=""
                      aria-hidden
                      draggable={false}
                      data-spin={spinning ? '' : undefined}
                    />
                  ) : (
                    <span className="relay__mark" aria-hidden>
                      {persona.glyph}
                    </span>
                  )}
                </span>
                <span className="relay__label machine">{station.label}</span>
                <span className="relay__kind machine">{persona.agent ? 'agent' : station.kind}</span>
                {station.id === 'board' && scars.length ? (
                  <span className="relay__scars machine">
                    {scars.map((n) => `✗${n}`).join(' ')}
                    {active?.outcome === 'passed' ? (
                      <span className="relay__scars-heal"> ✓ repaired</span>
                    ) : null}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {phase.sub ? (
        <div className="relay__now" data-tone={phase.tone} key={phase.activeStation ?? 'idle'}>
          <span className="relay__now-dot" aria-hidden />
          <span className="relay__now-text">{phase.sub}</span>
          {tools.length ? (
            <span className="relay__now-tools">
              {tools.slice(-3).map((t, k) => (
                <ToolChip key={k} entry={t} />
              ))}
            </span>
          ) : null}
        </div>
      ) : null}

      {repairing ? (
        <div className="relay__loop machine" data-active={phase.activeStation === 'medic' ? '' : undefined}>
          repair ↻ traceback → medic → board
        </div>
      ) : null}
    </div>
  );
}
