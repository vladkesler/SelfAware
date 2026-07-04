/**
 * Envelope guard. Structural check on {v, type, ts, seq, payload} only —
 * payloads of KNOWN types are trusted-with-cast (the backend is ours and one
 * meter away); UNKNOWN types become UnknownServerEvent and render as raw feed
 * rows, never dropped. Malformed JSON / bad envelope -> null (caller counts it).
 *
 * Deliberately no zod: the unknown-event escape hatch buys most of the safety
 * for zero dependencies on a 1-day build.
 */

import type { AnyEvent, ServerEvent } from '../types/events';
import { KNOWN_EVENT_TYPES } from '../types/events';

const KNOWN = new Set<string>(KNOWN_EVENT_TYPES);

export function parseServerEvent(raw: string): AnyEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== 'object' || data === null) return null;

  const env = data as Record<string, unknown>;
  if (
    env.v !== 1 ||
    typeof env.type !== 'string' ||
    typeof env.ts !== 'string' ||
    typeof env.seq !== 'number' ||
    typeof env.payload !== 'object' ||
    env.payload === null
  ) {
    return null;
  }

  if (KNOWN.has(env.type)) {
    return data as ServerEvent;
  }
  return { ...(data as object), __unknown: true } as AnyEvent;
}
