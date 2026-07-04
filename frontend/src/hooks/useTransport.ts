/**
 * useTransport — the SINGLE wiring point between transport and store:
 * createTransport once (singleton; StrictMode remounts reuse it), pipe every
 * event into store.apply, every status change into the connection slice,
 * and expose send(). Mounted by Console so the show starts at curtain-rise.
 */

import { useEffect } from 'react';
import type { ClientCommand } from '../types/events';
import { createTransport, getTransport, isMockMode } from '../lib/transport';
import { useStore } from '../state/store';

export function useTransport(): { send: (cmd: ClientCommand) => boolean } {
  useEffect(() => {
    const transport = createTransport(
      (ev) => useStore.getState().apply(ev),
      (status) => useStore.getState().setWsStatus(status),
      { onParseError: () => useStore.getState().noteParseError() },
    );
    useStore.getState().setMockMode(isMockMode());
    transport.start();
    return () => transport.stop();
  }, []);

  return { send: (cmd: ClientCommand) => getTransport().send(cmd) };
}
