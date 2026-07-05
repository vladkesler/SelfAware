/**
 * CenterStage — the theater. Mode is DERIVED:
 *   commission running / just-passed / failed  → RUN | SOURCE (split)
 *   idle with drivers                          → SCOPE GRID (multi-sensor)
 *   idle, empty registry                       → the invitation
 *
 * The split keeps the agent's actual work — the play-by-play and the driver
 * source — visible the whole time; a fast pass can no longer wipe it. On a
 * pass the split holds briefly (the run completes with an "admitted" line —
 * no badge; admission is the loop closing on the circuit + toolbelt + rail),
 * then settles to the live scope grid. On a failure the split stays, honest.
 */

import { useEffect, useMemo, useState } from 'react';
import { useCommission, useDrivers } from '../state/selectors';
import type { DriverCard } from '../types/domain';
import { AgentRun } from './AgentRun';
import { SourcePane } from './SourcePane';
import { ScopeGrid } from './ScopeGrid';

const PASS_HOLD_MS = 3400;

export function CenterStage() {
  const commission = useCommission();
  const drivers = useDrivers();
  const active = commission.active;

  // After a pass, hold the completed run/source briefly, then settle to grid.
  const [settled, setSettled] = useState(false);
  useEffect(() => setSettled(false), [active?.id]);
  useEffect(() => {
    if (active?.outcome === 'passed') {
      const id = setTimeout(() => setSettled(true), PASS_HOLD_MS);
      return () => clearTimeout(id);
    }
    return;
  }, [active?.outcome, active?.id]);

  const sensors = useMemo(
    () =>
      drivers.order
        .map((slug) => drivers.bySlug[slug])
        .filter((d): d is DriverCard => !!d && d.protocolClass !== 'output'),
    [drivers],
  );

  const mode =
    active && !active.outcome
      ? 'split'
      : active?.outcome === 'passed' && !settled
        ? 'split'
        : active?.outcome === 'failed'
          ? 'split'
          : drivers.order.length > 0
            ? 'grid'
            : 'idle';

  return (
    <div className="theater">
      <div className="theater__mode" key={mode === 'split' ? `split-${active?.id}` : mode}>
        {mode === 'split' && active ? (
          <div className="runsplit">
            <div className="runsplit__run">
              <AgentRun active={active} />
            </div>
            <div className="runsplit__source">
              <SourcePane active={active} />
            </div>
          </div>
        ) : null}
        {mode === 'grid' ? <ScopeGrid sensors={sensors} /> : null}
        {mode === 'idle' ? (
          <div className="theater__idle">plug something in — or ask the copilot</div>
        ) : null}
      </div>
    </div>
  );
}
