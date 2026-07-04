/**
 * Typed selector hooks + pure derivations. Hooks return SLICE REFERENCES
 * (stable until dispatch replaces them) — derive arrays in components with
 * useMemo keyed on the slice, never inside a zustand selector (fresh-array
 * selectors thrash useSyncExternalStore).
 */

import { PROTOCOL_VERSION } from '../types/events';
import { useStore } from './store';
import type { ActiveCommission } from './slices/commission';
import type { TermLine } from '../components/panels/TracebackPane';

export const useConnection = () => useStore((s) => s.connection);
export const useBoard = () => useStore((s) => s.board);
export const useCommission = () => useStore((s) => s.commission);
export const useDrivers = () => useStore((s) => s.drivers);
export const useReadingsMeta = () => useStore((s) => s.readings);
export const useChat = () => useStore((s) => s.chat);
export const useFeed = () => useStore((s) => s.feed);

export const useProtocolMismatch = (): boolean =>
  useStore(
    (s) => s.connection.server !== undefined && s.connection.server.protocol_v !== PROTOCOL_VERSION,
  );

/**
 * TracebackPane lines from the commission story: one meta line per stage
 * beat, with the VERBATIM traceback spliced in after the failing beat
 * (or appended while the failure beat is still in flight).
 */
export function buildTermLines(active: ActiveCommission | undefined): TermLine[] {
  if (!active) return [];
  const lines: TermLine[] = [];

  let lastFailedIdx = -1;
  active.trail.forEach((r, i) => {
    if (r.status === 'failed') lastFailedIdx = i;
  });

  active.trail.forEach((r, i) => {
    lines.push({
      kind: 'meta',
      at: r.at,
      text: `attempt ${r.attempt}/${active.maxAttempts} · ${r.stage} ${r.status}${r.detail ? ` — ${r.detail}` : ''}`,
    });
    if (i === lastFailedIdx && active.lastTraceback) {
      for (const tl of active.lastTraceback.split('\n')) {
        lines.push({ kind: 'stderr', at: r.at, text: tl });
      }
    }
  });

  if (lastFailedIdx === -1 && active.lastTraceback) {
    for (const tl of active.lastTraceback.split('\n')) {
      lines.push({ kind: 'stderr', at: '', text: tl });
    }
  }

  return lines;
}
