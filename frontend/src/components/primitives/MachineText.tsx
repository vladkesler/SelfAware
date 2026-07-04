/**
 * MachineText — monospace text with an optional typewriter reveal. Honors
 * prefers-reduced-motion: reveal becomes instant.
 */

import { useEffect, useState } from 'react';

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

export interface MachineTextProps {
  text: string;
  typewriter?: boolean | undefined;
  /** ms per character during the reveal. */
  charMs?: number | undefined;
  className?: string | undefined;
}

export function MachineText({ text, typewriter = false, charMs = 18, className }: MachineTextProps) {
  const reduced = usePrefersReducedMotion();
  const animate = typewriter && !reduced;
  const [shown, setShown] = useState<number>(animate ? 0 : text.length);

  useEffect(() => {
    if (!animate) {
      setShown(text.length);
      return;
    }
    setShown(0);
    const id = setInterval(() => {
      setShown((n) => {
        if (n >= text.length) {
          clearInterval(id);
          return n;
        }
        return n + 1;
      });
    }, charMs);
    return () => clearInterval(id);
  }, [text, animate, charMs]);

  return <span className={`machine${className ? ` ${className}` : ''}`}>{text.slice(0, shown)}</span>;
}
