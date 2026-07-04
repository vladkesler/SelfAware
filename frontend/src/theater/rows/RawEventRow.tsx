/**
 * RawEventRow — the universal fallback: event type + pretty-printed payload,
 * monospace. Unknown/unmapped event types degrade to "raw but visible" here;
 * nothing is ever dropped from the feed.
 */

import type { AnyEvent } from '../../types/events';

/** HH:MM:SS from an envelope ts — shared by the feed rows. */
export function tsClock(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString(undefined, { hour12: false });
}

export function RawEventRow({ event }: { event: AnyEvent }) {
  return (
    <div className="row machine">
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">{event.type}</span>
      <pre className="row__json">{JSON.stringify(event.payload, null, 2)}</pre>
    </div>
  );
}
