/**
 * Panel pulse — a tiny pub/sub OUTSIDE React state, fed from dispatch via the
 * theater registry. Every server event may name one panel whose chrome
 * flashes for var(--pulse-ms), in a semantic tone: live (orange) for life,
 * alert for the board's bad news. Panels opt in with usePanelPulse(id).
 */

import { useEffect, useState } from 'react';
import type { PanelId } from '../types/domain';

export type PulseTone = 'live' | 'alert';

type Listener = (tone: PulseTone) => void;

const listeners = new Map<PanelId, Set<Listener>>();

export function firePulse(id: PanelId, tone: PulseTone = 'live'): void {
  const set = listeners.get(id);
  if (!set) return;
  set.forEach((fn) => fn(tone));
}

function subscribe(id: PanelId, fn: Listener): () => void {
  let set = listeners.get(id);
  if (!set) {
    set = new Set();
    listeners.set(id, set);
  }
  set.add(fn);
  return () => {
    set.delete(fn);
  };
}

/** Duration from the --pulse-ms token; falls back to 180ms pre-mount. */
function pulseMs(): number {
  if (typeof document === 'undefined') return 180;
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--pulse-ms').trim();
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? n : 180;
}

/** The active pulse tone for this panel, or null. Clears after --pulse-ms. */
export function usePanelPulse(id: PanelId): PulseTone | null {
  const [tone, setTone] = useState<PulseTone | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = subscribe(id, (t) => {
      setTone(t);
      clearTimeout(timer);
      timer = setTimeout(() => setTone(null), pulseMs());
    });
    return () => {
      unsubscribe();
      clearTimeout(timer);
    };
  }, [id]);

  return tone;
}
