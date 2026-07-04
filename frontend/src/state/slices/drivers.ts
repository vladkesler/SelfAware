/**
 * Drivers slice — commissioned drivers (DriverCard) plus pre-commission
 * discovery presences (PresenceCard, "unidentified presence — commission?").
 * `order` preserves registration order for the DeviceRail.
 */

import type { DriverCard, PresenceCard } from '../../types/domain';

export interface DriversSlice {
  bySlug: Record<string, DriverCard>;
  presences: Record<string, PresenceCard>;
  order: string[];
}

export function initialDrivers(): DriversSlice {
  return { bySlug: {}, presences: {}, order: [] };
}

/** Presence key: "i2c:0x70" | "adc:27" (matches domain.ts PresenceCard.key). */
export function presenceKey(bus: 'i2c' | 'adc', addr?: number | null, pin?: number | null): string {
  if (bus === 'i2c') return `i2c:0x${(addr ?? 0).toString(16)}`;
  return `adc:${pin ?? '?'}`;
}
