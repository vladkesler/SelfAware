/**
 * TeaserStream — a miniature terminal on the landing page replaying
 * fixtures/teaser.json on loop through its OWN FixturePlayer (independent of
 * the app transport singleton — the teaser always runs, mock mode or not).
 */

import { useEffect, useState } from 'react';
import type { AnyEvent } from '../../types/events';
import { isKnownEvent } from '../../types/events';
import { FixturePlayer, type FixtureEntry } from '../../lib/fixturePlayer';
import teaser from '../../fixtures/teaser.json';

const MAX_LINES = 7;

interface TeaserLine {
  text: string;
  alert: boolean;
}

function toLine(ev: AnyEvent): TeaserLine {
  if (isKnownEvent(ev)) {
    switch (ev.type) {
      case 'system.hello':
        return { text: `session open · protocol v${ev.payload.protocol_v}`, alert: false };
      case 'commission.started':
        return {
          text: `commission ${ev.payload.slug} (${ev.payload.protocol_class})`,
          alert: false,
        };
      case 'commission.stage':
        return {
          text: `  ${ev.payload.stage} ▸ ${ev.payload.status}`,
          alert: ev.payload.status === 'failed',
        };
      case 'commission.traceback': {
        const lines = ev.payload.traceback.split('\n');
        return { text: `  ${lines[lines.length - 1] ?? 'Traceback'}`, alert: true };
      }
      case 'commission.passed':
        return { text: `✓ commissioned in ${ev.payload.attempts_used} attempts`, alert: false };
      case 'driver.registered':
        return { text: `+ tool ${ev.payload.tool_names[0] ?? ev.payload.slug} registered`, alert: false };
      case 'agent.thought':
        return { text: `~ ${ev.payload.text.slice(0, 56)}…`, alert: false };
      case 'sensor.reading':
        return {
          text: `${ev.payload.slug} → ${ev.payload.value} ${ev.payload.unit}`,
          alert: false,
        };
      default:
        return { text: ev.type, alert: false };
    }
  }
  return { text: ev.type, alert: false };
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
      {lines.map((line, i) => (
        <div key={i} className={`teaser__line${line.alert ? ' teaser__line--alert' : ''}`}>
          {line.text}
        </div>
      ))}
      <div className="teaser__line teaser__cursor">▌</div>
    </div>
  );
}
