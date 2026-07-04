/** Connection slice — transport status + protocol handshake bookkeeping. */

import type { SystemHello } from '../../types/events';
import type { WsStatus } from '../../lib/ws';

export interface ConnectionSlice {
  status: WsStatus;
  /** True when the FixturePlayer transport is live (?mock=1 / VITE_MOCK). */
  mock: boolean;
  /** Highest seq seen; gaps are legal (logged in dispatch, never fatal). */
  lastSeq: number;
  /** The last system.hello — carries protocol_v for the mismatch banner. */
  server?: SystemHello | undefined;
  /** Frames dropped by parseServerEvent (malformed JSON / bad envelope). */
  parseErrors: number;
}

export function initialConnection(): ConnectionSlice {
  return {
    status: 'closed',
    mock: false,
    lastSeq: 0,
    parseErrors: 0,
  };
}
