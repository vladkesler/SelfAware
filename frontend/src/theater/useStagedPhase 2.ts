/**
 * useStagedPhase — a minimum-dwell pacer for the relay. `derivePhase()` snaps to
 * the newest event instantly, so a fast burst of commission.stage events makes
 * the lit node jump around and a ring can start+stop before you can read it.
 *
 * This hook sits between derivePhase() and the render: it plays each DISTINCT
 * beat in order and holds it for at least MIN_STAGE_MS, so every agent's turn on
 * stage is legible and its ring spins long enough to register. Nothing is
 * skipped; if a backlog builds (e.g. a live backend narrating fast) the dwell
 * shortens to catch up, so it never lags reality for long. Same beat re-arriving
 * (identical station/tone/sub) is a no-op — sensor readings, which don't change
 * the beat, never perturb it. Mirrors the existing PASS_HOLD_MS hold pattern.
 */

import { useEffect, useRef, useState } from 'react';
import type { Phase } from './agents';

const MIN_STAGE_MS = 750;
const CATCHUP_MS = 320;
// The traceback hold (demo-runbook): the theater freezes on the red long enough
// to be read aloud. Alert beats never compress under backlog — on a live board
// this can lag the display ~1.5s per failure, but alert beats are bounded by
// max_attempts and every other beat still drains at CATCHUP_MS.
const ALERT_HOLD_MS = 2200;

/** Identity of a "beat" — what makes one relay state distinct from the next. */
function beat(p: Phase): string {
  return `${p.activeStation ?? '-'}|${p.tone}|${p.sub}`;
}

export function useStagedPhase(raw: Phase): Phase {
  const [shown, setShown] = useState<Phase>(raw);
  const queue = useRef<Phase[]>([]);
  const lastEnqueued = useRef<string>(beat(raw));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const play = () => {
      const next = queue.current.shift();
      if (!next) {
        timer.current = null;
        return;
      }
      setShown(next);
      const dwell =
        next.tone === 'alert'
          ? ALERT_HOLD_MS
          : queue.current.length > 2
            ? CATCHUP_MS
            : MIN_STAGE_MS;
      timer.current = setTimeout(play, dwell);
    };

    const b = beat(raw);
    if (b === lastEnqueued.current) return; // same beat — ignore (e.g. a reading)
    lastEnqueued.current = b;
    queue.current.push(raw);
    if (!timer.current) play();
  }, [raw]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return shown;
}
