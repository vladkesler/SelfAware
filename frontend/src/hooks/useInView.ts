/**
 * useInView — repeatable scroll reveal. Returns a ref to attach and whether
 * the element is currently intersecting the viewport threshold; toggles on
 * every crossing (scrolling away and back replays the reveal). Short-circuits
 * to `true` permanently under prefers-reduced-motion so nothing depends on
 * motion to become visible.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';

export function useInView<T extends HTMLElement>(threshold = 0.15): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const reduced =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const [inView, setInView] = useState(reduced);

  useEffect(() => {
    if (reduced || !ref.current) return;
    const el = ref.current;
    const io = new IntersectionObserver(([entry]) => {
      setInView(entry?.isIntersecting ?? false);
    }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [reduced, threshold]);

  return [ref, inView];
}
