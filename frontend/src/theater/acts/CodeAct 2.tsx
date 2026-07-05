/**
 * CodeAct — the driver source, revealed at generation speed (~2000 chars/s:
 * fast enough to never stall the demo, slow enough to read as writing).
 * A gate violation flags its line in alert and scrolls it into view.
 */

import { useEffect, useRef, useState } from 'react';
import { tokenizeLine } from '../../lib/syntax';

export interface CodeActProps {
  code: string;
  attempt: number;
  isRepair: boolean;
  /** 1-indexed line flagged by the static gate, if it rejected this code. */
  flagLine?: number | undefined;
}

const CHARS_PER_FRAME = 35;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export function CodeAct({ code, attempt, isRepair, flagLine }: CodeActProps) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? code.length : 0));
  const flagRef = useRef<HTMLDivElement>(null);
  const wellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(code.length);
      return;
    }
    setShown(0);
    let raf = 0;
    const step = () => {
      setShown((n) => {
        if (n >= code.length) return n;
        raf = requestAnimationFrame(step);
        return Math.min(n + CHARS_PER_FRAME, code.length);
      });
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [code]);

  const revealing = shown < code.length;

  // Keep the well pinned to the newest line while revealing.
  useEffect(() => {
    if (revealing && wellRef.current) wellRef.current.scrollTop = wellRef.current.scrollHeight;
  }, [shown, revealing]);

  useEffect(() => {
    if (!revealing && flagLine && flagRef.current) {
      flagRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [flagLine, revealing]);

  const lines = code.slice(0, shown).replace(/\n$/, '').split('\n');
  const lineCount = code.trim().split('\n').length;

  return (
    <div className="act act--code">
      <div className="act__head">
        driver source · {lineCount} lines
        <span className="act__tag">
          attempt {attempt}
          {isRepair ? ' · repaired' : ''}
        </span>
      </div>
      <div className="code-well" ref={wellRef}>
        {lines.map((line, i) => {
          const n = i + 1;
          const flagged = !revealing && flagLine === n;
          return (
            <div
              key={n}
              ref={flagged ? flagRef : null}
              className={`code-well__line${flagged ? ' code-well__line--flag' : ''}`}
            >
              <span className="code-well__num">{n}</span>
              <span>
                {tokenizeLine(line).map((tok, j) =>
                  tok.cls ? (
                    <span key={j} className={tok.cls}>
                      {tok.text}
                    </span>
                  ) : (
                    tok.text
                  ),
                )}
                {revealing && i === lines.length - 1 ? (
                  <span className="code-well__cursor">▌</span>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
