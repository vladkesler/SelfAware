/**
 * EventFeed — the mission log. Every known event narrates as one human
 * sentence (theater/narrate.ts) with click-to-expand raw JSON; consecutive
 * sensor.reading runs coalesce into a single in-place row (1 Hz × N sensors
 * would bury the story); commission.traceback keeps its dedicated verbatim
 * row; unknown types fall back to RawEventRow — raw but visible, never
 * dropped. Auto-scroll stays pinned unless the reader scrolled up.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../state/store';
import type { AnyEvent, EventOf } from '../types/events';
import { isKnownEvent } from '../types/events';
import { narrate, weightOf, type Narration, type LogWeight } from './narrate';
import { NarratedRow } from './rows/NarratedRow';
import { RawEventRow } from './rows/RawEventRow';
import { TracebackRow } from './rows/TracebackRow';

const PIN_THRESHOLD_PX = 32;

type Item =
  | { kind: 'narrated'; ev: AnyEvent; n: Narration; weight: LogWeight; count?: number }
  | { kind: 'traceback'; ev: EventOf<'commission.traceback'> }
  | { kind: 'raw'; ev: AnyEvent };

function buildItems(events: AnyEvent[]): Item[] {
  const items: Item[] = [];
  // Latest reading per slug within the current uninterrupted run.
  let run: { latest: Map<string, string>; count: number; ev: AnyEvent } | null = null;

  const flushRun = () => {
    if (!run) return;
    const text = [...run.latest.values()].join(' · ');
    items.push({
      kind: 'narrated',
      ev: run.ev,
      n: { tone: 'live', text },
      weight: 'normal',
      count: run.count,
    });
    run = null;
  };

  for (const ev of events) {
    if (!isKnownEvent(ev)) {
      flushRun();
      items.push({ kind: 'raw', ev });
      continue;
    }
    if (ev.type === 'sensor.reading') {
      const p = ev.payload;
      const line = `${p.slug} → ${p.value}${p.unit ? ` ${p.unit}` : ''}${p.plausible ? '' : ' ⚠'}`;
      if (!run) run = { latest: new Map(), count: 0, ev };
      run.latest.set(p.slug, line);
      run.count += 1;
      run.ev = ev;
      continue;
    }
    flushRun();
    if (ev.type === 'commission.traceback') {
      items.push({ kind: 'traceback', ev });
      continue;
    }
    const n = narrate(ev);
    if (n) items.push({ kind: 'narrated', ev, n, weight: weightOf(ev) });
  }
  flushRun();
  return items;
}

export function EventFeed() {
  const feed = useStore((s) => s.feed); // new slice ref per event
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [feed]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD_PX;
  };

  const items = buildItems(feed.events.toArray()); // oldest → newest

  return (
    <div className="feed" ref={scrollRef} onScroll={onScroll}>
      {items.length === 0 ? (
        <div className="feed__empty machine">the machine has said nothing yet</div>
      ) : (
        items.map((item) => {
          const key = `${item.ev.seq}:${item.ev.type}`;
          if (item.kind === 'traceback') return <TracebackRow key={key} event={item.ev} />;
          if (item.kind === 'raw') return <RawEventRow key={key} event={item.ev} />;
          return (
            <NarratedRow
              key={key}
              event={item.ev}
              tone={item.n.tone}
              text={item.n.text}
              weight={item.weight}
              count={item.count}
            />
          );
        })
      )}
    </div>
  );
}
