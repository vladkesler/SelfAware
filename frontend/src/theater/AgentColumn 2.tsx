/**
 * AgentColumn — the middle column's occupant, switched by context. During a
 * commission (and briefly after a pass) it shows the active agent's mind
 * (AUTHOR/MEDIC via AgentRun); when the bench is idle or has gone live it
 * becomes the PILOT console. One surface, always "the agent on stage."
 */

import { useEffect, useState } from 'react';
import type { ActiveCommission } from '../state/slices/commission';
import { AgentRun } from './AgentRun';
import { PilotConsole, type PilotConsoleProps } from './PilotConsole';

const PASS_HOLD_MS = 3400;

export function AgentColumn({
  active,
  pilot,
}: {
  active: ActiveCommission | undefined;
  pilot: PilotConsoleProps;
}) {
  const [settled, setSettled] = useState(false);
  useEffect(() => setSettled(false), [active?.id]);
  useEffect(() => {
    if (active?.outcome === 'passed') {
      const id = setTimeout(() => setSettled(true), PASS_HOLD_MS);
      return () => clearTimeout(id);
    }
    return;
  }, [active?.outcome, active?.id]);

  const showRun =
    !!active && (!active.outcome || active.outcome === 'failed' || !settled);

  return showRun && active ? <AgentRun active={active} /> : <PilotConsole {...pilot} />;
}
