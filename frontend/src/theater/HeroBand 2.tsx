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
import { TracebackMoment } from './TracebackMoment';
import { ReadingScope } from '../components/panels/ReadingScope';
import { HealthChip } from '../components/primitives/HealthChip';
import { useHealth } from '../state/selectors';
import type { ActiveCommission } from '../state/slices/commission';
import type { DriverCard, SensorHealthState } from '../types/domain';

/** The foot line: the honest health reason when it's not healthy, else identity. */
function signalFoot(
  card: DriverCard | undefined,
  health: SensorHealthState | undefined,
  isOutput: boolean,
): { text: string; status: string } {
  if (!card) return { text: 'commission a sensor to see it move', status: 'none' };
  const identity = `${card.displayName} · ${card.slug}`;
  if (isOutput || !health) return { text: identity, status: 'none' };
  if (health.status === 'critical' || health.status === 'degrading') {
    const reason = health.reasons[0] ?? identity;
    const eta = health.trend.direction === 'degrading' && health.trend.note ? ` · ${health.trend.note}` : '';
    return { text: `${reason}${eta}`, status: health.status };
  }
  if (health.status === 'unknown') {
    return {
      text: `calibrating — ${health.readingsCount}/${health.baselineTarget} readings to a health verdict`,
      status: 'none',
    };
  }
  return { text: identity, status: 'none' }; // healthy: stay calm, name the part
}

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

  const health = useHealth().bySlug[focusSlug ?? ''];
  const foot = signalFoot(focusCard, health, isOutput);

  return (
    <div className="hero" data-tone={phase.tone}>
      <div className="hero__main">
        <AgentRelay phase={phase} active={active} />
        <TracebackMoment phase={phase} active={active} />
      </div>

      <aside className="hero__signal" data-tone={phase.tone}>
        <div className="hero__signal-head machine">
          <span className="hero__signal-title">SIGNAL</span>
          <span className="hero__signal-head-right">
            {focusSlug && !isOutput ? <HealthChip health={health} /> : null}
            <span className="hero__signal-board">{boardLabel}</span>
          </span>
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
        <div className="hero__signal-foot machine" data-status={foot.status}>
          {foot.text}
        </div>
      </aside>
    </div>
  );
}
