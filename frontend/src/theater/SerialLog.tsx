/**
 * SerialLog — the milestone strip. NOT the old firehose: only the beats that
 * matter, each one attempt-tagged (A1/A2…) and role-glyphed, terse enough to
 * read at a glance. SCANNED · WROTE · TRACEBACK · REPAIRED · PASSED · ADMITTED,
 * plus every agent tool RESULT (AUTHOR/MEDIC dry_gate, PILOT read_/set_) so the
 * hands show here too. Newest at the bottom; auto-scroll pinned.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../state/store';
import type { AnyEvent } from '../types/events';
import { isKnownEvent, normalizeAgent } from '../types/events';
import { PERSONAS, type AgentKey } from './agents';
import type { LogTone } from './narrate';

interface SerialLine {
  key: string;
  tag: string;
  role: AgentKey;
  text: string;
  tone: LogTone;
}

function trunc(s: string, n: number): string {
  const one = s.replace(/\s+/g, ' ').trim();
  return one.length > n ? `${one.slice(0, n)}…` : one;
}

function lastLine(s: string): string {
  const parts = s.trim().split('\n');
  return trunc(parts[parts.length - 1] ?? '', 40);
}

function serialLine(ev: AnyEvent): SerialLine | null {
  if (!isKnownEvent(ev)) return null;
  const key = `${ev.seq}:${ev.type}`;
  switch (ev.type) {
    case 'discovery.device_found': {
      const p = ev.payload;
      const where = p.bus === 'i2c' ? `0x${(p.addr ?? 0).toString(16)}` : `GP${p.pin ?? '?'}`;
      return { key, tag: 'scan', role: 'host', tone: 'live', text: `${p.identity ?? 'unknown part'} · ${where}` };
    }
    case 'commission.started': {
      const p = ev.payload;
      return { key, tag: 'A1', role: 'host', tone: 'charge', text: `commission ${p.slug} · ${p.protocol_class}` };
    }
    case 'commission.stage': {
      const p = ev.payload;
      const tag = `A${p.attempt}`;
      if (p.stage === 'generate' && p.status === 'passed')
        return { key, tag, role: 'author', tone: 'live', text: 'wrote the driver' };
      if (p.stage === 'repair' && p.status === 'passed')
        return { key, tag, role: 'medic', tone: 'live', text: 'repaired the driver' };
      if (p.stage === 'validate' && p.status === 'failed')
        return { key, tag, role: 'host', tone: 'alert', text: `gate rejected · ${trunc(p.detail, 34)}` };
      if (p.stage === 'test' && p.status === 'passed')
        return { key, tag, role: 'board', tone: 'live', text: `passed · ${p.detail.replace('reading=', '') || 'ok'}` };
      return null;
    }
    case 'commission.traceback': {
      const p = ev.payload;
      return { key, tag: `A${p.attempt}`, role: 'board', tone: 'alert', text: `traceback · ${lastLine(p.traceback)}` };
    }
    case 'driver.registered': {
      const p = ev.payload;
      return { key, tag: 'admit', role: 'host', tone: 'live', text: `admitted · ${p.tool_names.join(', ')}` };
    }
    case 'commission.passed': {
      const p = ev.payload;
      return { key, tag: 'live', role: 'board', tone: 'live', text: `verified · ${p.reading ?? ''}${p.unit ? ` ${p.unit}` : ''}` };
    }
    case 'commission.failed': {
      const p = ev.payload;
      return { key, tag: 'fail', role: 'board', tone: 'alert', text: `not admitted · ${trunc(p.reason, 34)}` };
    }
    case 'agent.tool_result': {
      const p = ev.payload;
      const role = normalizeAgent(p.agent);
      return {
        key,
        tag: 'tool',
        role,
        tone: p.ok ? 'live' : 'alert',
        text: `${p.tool} ${p.ok ? '✓' : '✗'}${p.preview ? ` → ${trunc(p.preview, 24)}` : ''}`,
      };
    }
    default:
      return null;
  }
}

export function SerialLog() {
  const feed = useStore((s) => s.feed);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [feed]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
  };

  const lines: SerialLine[] = [];
  feed.events.forEach((ev) => {
    const l = serialLine(ev);
    if (l) lines.push(l);
  });

  return (
    <div className="serial" ref={scrollRef} onScroll={onScroll}>
      {lines.length === 0 ? (
        <div className="serial__empty machine">standing by…</div>
      ) : (
        lines.map((l, i) => (
          <div className="serial__row" key={`${l.key}:${i}`} data-tone={l.tone}>
            <span className="serial__tag machine">{l.tag}</span>
            <span className="serial__glyph machine" data-role={l.role}>
              {PERSONAS[l.role].glyph}
            </span>
            <span className="serial__text machine">{l.text}</span>
          </div>
        ))
      )}
    </div>
  );
}
