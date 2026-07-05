/**
 * SourcePane — the driver the agent wrote, ALWAYS visible while a commission
 * is on stage (and held after it passes). A fast single-attempt pass can no
 * longer wipe the code before anyone reads it. Streams during generation,
 * swaps per attempt, flags the gate-rejected line. Reuses CodeAct.
 */

import type { ActiveCommission } from '../state/slices/commission';
import { CodeAct } from './acts/CodeAct';

export function SourcePane({ active }: { active: ActiveCommission }) {
  const attempt = active.attempt;
  const entry = active.codeByAttempt[attempt];

  // A gate rejection names the offending line — flag it in the source.
  const validate = [...active.trail]
    .reverse()
    .find((r) => r.attempt === attempt && r.stage === 'validate' && r.status === 'failed');
  const flagMatch = validate?.detail?.match(/line (\d+)/);
  const flagLine = flagMatch?.[1] ? Number(flagMatch[1]) : undefined;

  if (!entry) {
    return (
      <div className="source-pane source-pane--empty machine">
        {active.outcome ? 'no source captured' : 'the agent is composing the driver…'}
      </div>
    );
  }

  return (
    <div className="source-pane">
      <CodeAct
        code={entry.code}
        attempt={attempt}
        isRepair={entry.isRepair}
        {...(flagLine !== undefined ? { flagLine } : {})}
      />
    </div>
  );
}
