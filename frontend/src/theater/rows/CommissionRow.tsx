/** CommissionRow — one stage beat: "attempt 1 · generate ▸ passed". */

import type { EventOf } from '../../types/events';
import { tsClock } from './RawEventRow';

export function CommissionRow({ event }: { event: EventOf<'commission.stage'> }) {
  const { attempt, stage, status, detail } = event.payload;
  const tone = status === 'failed' ? 'row--alert' : status === 'passed' ? 'row--live' : '';
  return (
    <div className={`row machine ${tone}`}>
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">commission</span>
      <span>
        attempt {attempt} · {stage} ▸ {status}
        {detail ? <span className="row__detail"> — {detail}</span> : null}
      </span>
    </div>
  );
}
