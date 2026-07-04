/**
 * TracebackPane — the machine's own voice. stderr lines are VERBATIM board
 * output: pre-wrap, never trimmed, never re-wrapped, in the reserved alert
 * red. meta lines narrate stage beats in muted phosphor.
 */

import { useEffect, useRef } from 'react';

export interface TermLine {
  kind: 'stdout' | 'stderr' | 'meta';
  text: string;
  at: string;
}

export interface TracebackPaneProps {
  lines: TermLine[];
  live: boolean;
}

export function TracebackPane({ lines, live }: TracebackPaneProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div className="term machine" ref={ref}>
      {lines.length === 0 ? (
        <div className="term__line term__line--meta">— board stderr will appear here, verbatim —</div>
      ) : (
        lines.map((line, i) => (
          <pre key={i} className={`term__line term__line--${line.kind}`}>
            {line.text || ' '}
          </pre>
        ))
      )}
      {live ? <span className="term__cursor">▌</span> : null}
    </div>
  );
}
