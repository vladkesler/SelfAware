/**
 * TracebackRow — the board's own words. VERBATIM stderr: pre-wrap, never
 * trimmed, never re-wrapped, alert color (the one reserved use of --alert).
 */

import type { EventOf } from '../../types/events';
import { tsClock } from './RawEventRow';

export function TracebackRow({ event }: { event: EventOf<'commission.traceback'> }) {
  const { attempt, stage, traceback } = event.payload;
  return (
    <div className="row machine row--alert">
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">traceback</span>
      <div>
        <span className="row__detail">
          attempt {attempt} · stage {stage} — board stderr, verbatim:
        </span>
        <pre className="row__traceback">{traceback}</pre>
      </div>
    </div>
  );
}
