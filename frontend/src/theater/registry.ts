/**
 * Theater registry — THE event→presentation seam. For each event type:
 *   Row    how the event appears in the play-by-play feed (omit → RawEventRow)
 *   pulse  which panel's chrome flashes when it lands (fired from dispatch)
 *
 * Adding a new event on build day = one entry here + one case in dispatch.ts.
 */

import type { ComponentType } from 'react';
import type { AnyEvent, EventOf, EventType } from '../types/events';
import type { PanelId } from '../types/domain';
import { RawEventRow } from './rows/RawEventRow';
import { CommissionRow } from './rows/CommissionRow';
import { TracebackRow } from './rows/TracebackRow';
import { AgentThoughtRow } from './rows/AgentThoughtRow';
import { ToolCallRow } from './rows/ToolCallRow';
import { ReadingRow } from './rows/ReadingRow';

export type RowComponent = ComponentType<{ event: AnyEvent }>;

export interface RegistryEntry<T extends EventType = EventType> {
  Row?: ComponentType<{ event: EventOf<T> }>;
  pulse?: PanelId;
}

export const registry: { [T in EventType]?: RegistryEntry<T> } = {
  'commission.stage': { Row: CommissionRow, pulse: 'stepper' },
  'commission.traceback': { Row: TracebackRow, pulse: 'terminal' },
  'agent.thought': { Row: AgentThoughtRow },
  'agent.tool_call': { Row: ToolCallRow },
  'sensor.reading': { Row: ReadingRow, pulse: 'scope' },
  'driver.registered': { pulse: 'rail' },
  'discovery.device_found': { pulse: 'rail' },
  // Build day fills the rest; anything absent → RawEventRow, no pulse.
};

/** Feed row for an event type; unknown/unmapped types fall back to RawEventRow. */
export function resolveRow(type: string): RowComponent {
  const entry = (registry as Record<string, RegistryEntry | undefined>)[type];
  return (entry?.Row ?? RawEventRow) as RowComponent;
}

/** Pulse target for an event type, if any. */
export function resolvePulse(type: string): PanelId | undefined {
  return (registry as Record<string, RegistryEntry | undefined>)[type]?.pulse;
}
