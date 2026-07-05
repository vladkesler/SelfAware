/**
 * useScrollProgress — 0..1 as the user scrolls through the first `distance`
 * px of the page. Drives the hero's scroll-scrubbed fade/parallax on the way
 * out, rather than a fixed-duration CSS transition. Short-circuits to 0
 * (static, no fade) under prefers-reduced-motion.
 */
import { useEffect, useState } from 'react';

export function useScrollProgress(distance = window.innerHeight * 0.7): number {
  const reduced =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (reduced) return;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        setProgress(Math.min(1, Math.max(0, window.scrollY / distance)));
        ticking = false;
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [reduced, distance]);

  return reduced ? 0 : progress;
}
