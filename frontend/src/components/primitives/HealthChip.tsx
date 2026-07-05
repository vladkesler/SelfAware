/**
 * HealthChip — the sensor's vitals annunciator. An instrument LED + a
 * tracked-caps word: the DOT carries the color (healthy → signal-orange heartbeat,
 * degrading → charge, critical → alert, unknown/actuator → dim), the label
 * lights only when it demands attention. Green stays scarce — the chip is a
 * readout, not a lit container. `unknown` reads as BASELINE n/target, an honest
 * "still gathering" rather than a scary "unknown". Full reasons on hover.
 */

import { StatusDot, type DotState } from './StatusDot';
import type { HealthStatus, SensorHealthState } from '../../types/domain';

const DOT: Record<HealthStatus, DotState> = {
  healthy: 'live',
  degrading: 'busy',
  critical: 'alert',
  unknown: 'idle',
  not_monitored: 'idle',
};

const LABEL: Record<HealthStatus, string> = {
  healthy: 'HEALTHY',
  degrading: 'DEGRADING',
  critical: 'CRITICAL',
  unknown: 'BASELINE',
  not_monitored: 'ACTUATOR',
};

export function HealthChip({ health }: { health: SensorHealthState | undefined }) {
  const status: HealthStatus = health?.status ?? 'unknown';
  const label =
    status === 'unknown' && health && health.baselineTarget > 0
      ? `BASELINE ${health.readingsCount}/${health.baselineTarget}`
      : LABEL[status];
  const title = health && health.reasons.length ? health.reasons.join(' · ') : undefined;
  return (
    <span className="health-chip machine" data-status={status} title={title}>
      <StatusDot state={DOT[status]} />
      <span className="health-chip__label">{label}</span>
    </span>
  );
}
