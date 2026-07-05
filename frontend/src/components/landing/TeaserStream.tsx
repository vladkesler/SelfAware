/**
 * TeaserStream — a miniature terminal on the landing page replaying
 * fixtures/teaser.json on loop through its OWN FixturePlayer (independent of
 * the app transport singleton — the teaser always runs, mock mode or not).
 */

import { useEffect, useState } from 'react';
import type { AnyEvent } from '../../types/events';
import { isKnownEvent } from '../../types/events';
import { FixturePlayer, type FixtureEntry } from '../../lib/fixturePlayer';
import { StatusDot } from '../primitives/StatusDot';
import teaser from '../../fixtures/teaser.json';

const MAX_LINES = 7;

type LineKind = 'default' | 'thought' | 'stage';

interface TeaserLine {
  text: string;
  alert: boolean;
  kind: LineKind;
}

function toLine(ev: AnyEvent): TeaserLine {
  if (isKnownEvent(ev)) {
    switch (ev.type) {
      case 'system.hello':
        return { text: `session open · protocol v${ev.payload.protocol_v}`, alert: false, kind: 'default' };
      case 'commission.started':
        return {
          text: `commission ${ev.payload.slug} (${ev.payload.protocol_class})`,
          alert: false,
          kind: 'default',
        };
      case 'commission.stage':
        return {
          text: `  ${ev.payload.stage} ▸ ${ev.payload.status}`,
          alert: ev.payload.status === 'failed',
          kind: 'stage',
        };
      case 'commission.traceback': {
        const lines = ev.payload.traceback.split('\n');
        return { text: `  ${lines[lines.length - 1] ?? 'Traceback'}`, alert: true, kind: 'stage' };
      }
      case 'commission.passed':
        return {
          text: `✓ commissioned in ${ev.payload.attempts_used} attempts`,
          alert: false,
          kind: 'default',
        };
      case 'driver.registered':
        return {
          text: `+ tool ${ev.payload.tool_names[0] ?? ev.payload.slug} registered`,
          alert: false,
          kind: 'default',
        };
      case 'agent.thought':
        return { text: `~ ${ev.payload.text.slice(0, 56)}…`, alert: false, kind: 'thought' };
      case 'sensor.reading':
        return {
          text: `${ev.payload.slug} → ${ev.payload.value} ${ev.payload.unit}`,
          alert: false,
          kind: 'default',
        };
      default:
        return { text: ev.type, alert: false, kind: 'default' };
    }
  }
  return { text: ev.type, alert: false, kind: 'default' };
}

function lineClassName(line: TeaserLine): string {
  if (line.alert) return ' teaser__line--alert';
  if (line.kind === 'thought') return ' teaser__line--thought';
  if (line.kind === 'stage') return ' teaser__line--stage';
  return '';
}

export function TeaserStream() {
  const [lines, setLines] = useState<TeaserLine[]>([]);

  useEffect(() => {
    const player = new FixturePlayer(teaser as unknown as FixtureEntry[], {
      loop: true,
      onEvent: (ev) => setLines((prev) => [...prev.slice(-(MAX_LINES - 1)), toLine(ev)]),
    });
    player.start();
    return () => player.stop();
  }, []);

  return (
    <div className="teaser machine" aria-hidden="true">
      <div className="teaser__bar">
        <StatusDot state="live" />
        <span className="teaser__title">agent · commissioning ldr</span>
      </div>
      <div className="teaser__body">
        {lines.map((line, i) => (
          <div key={i} className={`teaser__line${lineClassName(line)}`}>
            {line.text}
          </div>
        ))}
        <div className="teaser__line teaser__cursor">▌</div>
      </div>
    </div>
  );
}
