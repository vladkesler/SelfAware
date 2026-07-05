/**
 * Theater registry — THE event→presentation seam, now pulse-only: for each
 * event type, which panel's chrome flashes and in which semantic tone.
 * (Feed rendering lives in EventFeed + narrate.ts — every known event
 * narrates; unknown types fall back to a raw row there.)
 */

import type { EventType } from '../types/events';
import type { PanelId } from '../types/domain';
import type { PulseTone } from './pulse';

export interface RegistryEntry {
  pulse?: PanelId;
  /** Semantic tone of the pulse; defaults to live. */
  pulseTone?: PulseTone;
}

export const registry: Partial<Record<EventType, RegistryEntry>> = {
  'commission.stage': { pulse: 'stepper' },
  'commission.code': { pulse: 'stepper' },
  'commission.traceback': { pulse: 'terminal', pulseTone: 'alert' },
  'commission.passed': { pulse: 'stepper' },
  'commission.failed': { pulse: 'stepper', pulseTone: 'alert' },
  // sensor.reading: deliberately NO pulse — the moving trace IS the life signal.
  'driver.registered': { pulse: 'rail' },
  'discovery.device_found': { pulse: 'rail' },
};

/** Pulse target + tone for an event type, if any. */
export function resolvePulse(type: string): { id: PanelId; tone: PulseTone } | undefined {
  const entry = (registry as Record<string, RegistryEntry | undefined>)[type];
  if (!entry?.pulse) return undefined;
  return { id: entry.pulse, tone: entry.pulseTone ?? 'live' };
}
