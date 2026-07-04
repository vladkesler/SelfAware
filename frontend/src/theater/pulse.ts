/**
 * Panel pulse — a tiny pub/sub OUTSIDE React state, fed from dispatch via the
 * theater registry. Every server event may name one panel whose chrome
 * flashes for var(--pulse-ms). Panels opt in with usePanelPulse(id).
 */

import { useEffect, useState } from 'react';
import type { PanelId } from '../types/domain';

type Listener = () => void;

const listeners = new Map<PanelId, Set<Listener>>();

export function firePulse(id: PanelId): void {
  const set = listeners.get(id);
  if (!set) return;
  set.forEach((fn) => fn());
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

/** True while this panel should glow. Flips back after --pulse-ms. */
export function usePanelPulse(id: PanelId): boolean {
  const [on, setOn] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = subscribe(id, () => {
      setOn(true);
      clearTimeout(timer);
      timer = setTimeout(() => setOn(false), pulseMs());
    });
    return () => {
      unsubscribe();
      clearTimeout(timer);
    };
  }, [id]);

  return on;
}
