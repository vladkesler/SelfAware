/**
 * EventTransport — the seam that makes the real WebSocket and the fixture
 * player interchangeable. Chosen once at boot: FixturePlayer when `?mock=1`
 * or VITE_MOCK==='1', else SocketClient against VITE_WS_URL.
 *
 * Everything downstream (store, panels) only ever sees AnyEvent + WsStatus;
 * nothing outside this module knows which transport is live.
 */

import type { AnyEvent, ClientCommand } from '../types/events';
import { SocketClient, type WsStatus } from './ws';
import { FixturePlayer, type FixtureEntry } from './fixturePlayer';
import commissionLdr from '../fixtures/commission-ldr.json';

export interface EventTransport {
  start(): void;
  stop(): void;
  /** Returns false when not connected/open. No queueing — UI disables inputs. */
  send(cmd: ClientCommand): boolean;
}

export interface TransportExtras {
  /** Called once per dropped (unparseable) frame; UI counts them. */
  onParseError?: (() => void) | undefined;
}

/** True when the app should run against fixtures instead of the backend. */
export function isMockMode(): boolean {
  if (typeof window !== 'undefined') {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('mock') === '1') return true;
  }
  return import.meta.env.VITE_MOCK === '1';
}

let singleton: EventTransport | null = null;

export function createTransport(
  sink: (ev: AnyEvent) => void,
  onStatus: (s: WsStatus) => void,
  extras?: TransportExtras,
): EventTransport {
  if (singleton) return singleton; // created once; StrictMode remounts reuse it
  if (isMockMode()) {
    singleton = new FixturePlayer(commissionLdr as unknown as FixtureEntry[], {
      onEvent: sink,
      onStatus,
    });
  } else {
    const url = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'ws://localhost:8000/ws';
    singleton = new SocketClient({
      url,
      onEvent: sink,
      onStatus,
      ...(extras?.onParseError ? { onParseError: extras.onParseError } : {}),
    });
  }
  return singleton;
}

/** Singleton accessor so any panel can send() without prop-drilling. */
export function getTransport(): EventTransport {
  if (!singleton) {
    throw new Error('getTransport() before createTransport() — wire useTransport() first');
  }
  return singleton;
}
