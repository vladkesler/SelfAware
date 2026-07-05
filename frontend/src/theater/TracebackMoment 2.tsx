/**
 * TracebackMoment — the break→fix beat, made unmissable. Renders only during
 * the two beats that matter: the BREAK (the board rejected the driver — the
 * reserved red, the headline, the verbatim final exception line) and the FIX
 * (the same error, now in the medic's hands — charge tone, handoff glyph).
 * Pure derivation from the staged phase + commission state: it appears because
 * the board really raised, never on a timer.
 */

import { PERSONAS, type Phase } from './agents';
import type { ActiveCommission } from '../state/slices/commission';

/** The board's last word: final exception line of the verbatim traceback,
 *  falling back to the failed stage's detail (timeouts raise no traceback). */
function boardError(active: ActiveCommission | undefined): string | null {
  if (!active) return null;
  const tb = active.tracebackByAttempt[active.attempt] ?? active.lastTraceback;
  if (tb) {
    const lines = tb.trimEnd().split('\n');
    return lines[lines.length - 1] || null;
  }
  for (let i = active.trail.length - 1; i >= 0; i--) {
    const r = active.trail[i];
    if (r.status === 'failed' && r.detail) return r.detail;
  }
  return null;
}

export function TracebackMoment({
  phase,
  active,
}: {
  phase: Phase;
  active: ActiveCommission | undefined;
}) {
  const error = boardError(active);
  const isBreak = phase.tone === 'alert' && phase.agentKey === 'board';
  const isFix =
    !isBreak && phase.activeStation === 'medic' && !active?.outcome && !!error;
  if (!isBreak && !isFix) return null;

  const beat = isBreak ? 'break' : 'fix';
  const glyph = isBreak ? PERSONAS.board.glyph : PERSONAS.medic.glyph;
  return (
    <div className="tbmoment machine" data-beat={beat} key={beat}>
      <div className="tbmoment__head">
        <span className="tbmoment__glyph" aria-hidden>
          {glyph}
        </span>
        <span className="tbmoment__headline">{phase.headline}</span>
      </div>
      {error ? (
        <pre className="tbmoment__line">
          {isFix ? '→ ' : ''}
          {error}
        </pre>
      ) : null}
    </div>
  );
}
