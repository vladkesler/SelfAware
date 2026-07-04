/** ReadingRow — one live sample; plausibility is the HOST's verdict. */

import type { EventOf } from '../../types/events';
import { tsClock } from './RawEventRow';

export function ReadingRow({ event }: { event: EventOf<'sensor.reading'> }) {
  const { slug, value, unit, plausible } = event.payload;
  return (
    <div className={`row machine ${plausible ? 'row--live' : 'row--alert'}`}>
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">{slug}</span>
      <span>
        {value} {unit} {plausible ? '' : '⚠ implausible'}
      </span>
    </div>
  );
}
