/**
 * Frontend-side domain types — what the store slices hold after events are
 * applied. Wire types live in ./events.ts; these are their accumulated forms.
 */

import type { ProtocolClass, Stage, StageStatus } from './events';

export type { PanelId } from './events';

export interface DriverCard {
  slug: string;
  displayName: string;
  protocolClass: ProtocolClass;
  pins: Record<string, number>;
  toolNames: string[];
  codeHash: string;
  unit: string;
  status: 'live' | 'repairing';
  lastReading?: number;
}

/** An unidentified-or-identified presence from discovery.* (pre-commission). */
export interface PresenceCard {
  key: string; // "i2c:0x70" | "adc:27"
  bus: 'i2c' | 'adc';
  addr?: number;
  pin?: number;
  identity?: string;
  confidence: 'exact' | 'unknown';
  suggestedSpec?: Record<string, unknown>;
}

export interface ReadingPoint {
  t: number; // epoch ms (client receive time)
  v: number;
  plausible: boolean;
}

export interface StageRecord {
  stage: Stage;
  status: StageStatus;
  attempt: number;
  at: string; // event ts
  detail?: string;
}

export interface ChatMessage {
  role: 'user' | 'agent';
  text: string;
  at: string;
}
