/**
 * EventFeed — the play-by-play. Renders the feed ring newest-LAST through the
 * theater registry (unknown/unmapped types → RawEventRow). Auto-scroll stays
 * pinned to the bottom unless the user has scrolled up to read history.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../state/store';
import { resolveRow } from './registry';

const PIN_THRESHOLD_PX = 32;

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

  const events = feed.events.toArray(); // oldest → newest

  return (
    <div className="feed" ref={scrollRef} onScroll={onScroll}>
      {events.length === 0 ? (
        <div className="feed__empty machine">awaiting events…</div>
      ) : (
        events.map((ev) => {
          const Row = resolveRow(ev.type);
          return <Row key={`${ev.seq}:${ev.type}`} event={ev} />;
        })
      )}
    </div>
  );
}
