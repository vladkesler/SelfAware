/**
 * Health slice — the latest sensor.health verdict per slug.
 *
 * Parallel to the readings slice but low-frequency: the backend only pushes on
 * a coarse verdict change (and replays current verdicts on connect), so this
 * updates a handful of times per sensor, not per sample. Plain immutable
 * replace — no ring, no hot path.
 */

import type { SensorHealthState } from '../../types/domain';

export interface HealthSlice {
  bySlug: Record<string, SensorHealthState>;
}

export function initialHealth(): HealthSlice {
  return { bySlug: {} };
}
