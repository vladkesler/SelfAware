/**
 * NarratedRow — one mission-log line: tone tick · clock · sentence, with
 * click-to-expand raw JSON (the honesty affordance: every narration can be
 * audited against the wire).
 */

import { useState } from 'react';
import type { AnyEvent } from '../../types/events';
import type { LogTone, LogWeight } from '../narrate';
import { tsClock } from './RawEventRow';

export interface NarratedRowProps {
  event: AnyEvent;
  tone: LogTone;
  text: string;
  weight?: LogWeight | undefined;
  /** Coalesced-run counter (sensor readings); shown as ×N. */
  count?: number | undefined;
}

export function NarratedRow({ event, tone, text, weight = 'normal', count }: NarratedRowProps) {
  const [open, setOpen] = useState(false);
  const toneClass = tone === 'neutral' ? '' : ` row--${tone}`;
  const weightClass = weight === 'normal' ? '' : ` row--${weight}`;
  const lane = event.type.split('.')[0];

  return (
    <div>
      <button
        type="button"
        className={`row machine${toneClass}${weightClass}`}
        onClick={() => setOpen((v) => !v)}
        title="click to inspect the raw event"
      >
        {weight === 'milestone' ? <span className="row__marker" aria-hidden="true">▸</span> : null}
        <span className="row__ts">{tsClock(event.ts)}</span>
        <span className="row__type">{lane}</span>
        <span>{text}</span>
        {count !== undefined && count > 1 ? <span className="row__count">×{count}</span> : null}
      </button>
      {open ? (
        <pre className="row__expand machine">{JSON.stringify(event.payload, null, 2)}</pre>
      ) : null}
    </div>
  );
}
