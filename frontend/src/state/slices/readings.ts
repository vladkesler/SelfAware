/**
 * Readings slice — per-slug ring buffers for the oscilloscope.
 *
 * HOT PATH RULES: rings are mutated in place (never re-allocated per sample);
 * `version[slug]` bumps on every push so the ReadingScope's rAF loop can
 * cheaply detect fresh data via a transient store.subscribe — no React
 * re-render per sample flows through this slice.
 */

import type { ReadingPoint } from '../../types/domain';
import { RingBuffer } from '../../lib/ring';

export const READINGS_CAP = 512;

export interface ReadingsSlice {
  bySlug: Record<string, RingBuffer<ReadingPoint>>;
  version: Record<string, number>;
}

export function initialReadings(): ReadingsSlice {
  return { bySlug: {}, version: {} };
}
