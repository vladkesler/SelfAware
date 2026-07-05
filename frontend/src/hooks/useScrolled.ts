/**
 * useScrolled — true once the page has scrolled past `threshold` px. Backs
 * the Navbar's transparent -> frosted-glass transition.
 */
import { useEffect, useState } from 'react';

export function useScrolled(threshold = 32): boolean {
  const [scrolled, setScrolled] = useState(() => window.scrollY > threshold);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [threshold]);

  return scrolled;
}
