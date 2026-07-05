/**
 * HeroBand — the focal region. No billboard: the relay shows the cast and the
 * hand-offs, and the lit agent carries its own caption + tool chips (what's
 * happening now). The SIGNAL card on the right is the un-fakeable "it is alive"
 * proof — the live reading coming off the real board. One focal point that
 * follows the story: the working agent during a commission, the signal once live.
 */

import { derivePhase } from './agents';
import { useStagedPhase } from './useStagedPhase';
import { AgentRelay } from './AgentRelay';
import { ReadingScope } from '../components/panels/ReadingScope';
import type { ActiveCommission } from '../state/slices/commission';
import type { DriverCard } from '../types/domain';

export interface HeroBandProps {
  active: ActiveCommission | undefined;
  drivers: DriverCard[];
  boardLabel: string;
}

export function HeroBand({ active, drivers, boardLabel }: HeroBandProps) {
  const phase = useStagedPhase(derivePhase(active, drivers.length));

  // The SILICON card focuses the commissioning part, else the newest live sensor.
  const focusSlug = active?.slug ?? drivers[drivers.length - 1]?.slug;
  const focusCard = drivers.find((d) => d.slug === focusSlug);
  const unit = focusCard?.unit || active?.finalUnit || '';
  const isOutput = focusCard?.protocolClass === 'output';

  return (
    <div className="hero">
      <div className="hero__main">
        <AgentRelay phase={phase} active={active} />
      </div>

      <aside className="hero__signal" data-tone={phase.tone}>
        <div className="hero__signal-head machine">
          <span className="hero__signal-title">SIGNAL</span>
          <span className="hero__signal-board">{boardLabel}</span>
        </div>
        <div className="hero__signal-scope">
          {focusSlug && !isOutput ? (
            <ReadingScope slug={focusSlug} unit={unit} hero />
          ) : (
            <div className="hero__signal-empty machine">
              {isOutput ? focusCard?.displayName : 'no signal yet'}
            </div>
          )}
        </div>
        <div className="hero__signal-foot machine">
          {focusCard
            ? `${focusCard.displayName} · ${focusCard.slug}`
            : 'commission a sensor to see it move'}
        </div>
      </aside>
    </div>
  );
}
