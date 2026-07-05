/**
 * CommissionCircuit — the loop rendered as a living signal path. Current
 * (charge dashes) flows into the active node; judged nodes snap orange or
 * alert; REPAIR is a return trace curving under the path back to GENERATE;
 * every attempt leaves a permanent scar under the node where it died.
 * Derived purely from commission.active.trail + history — zero new state.
 *
 * Geometry: the SVG underlay stretches (preserveAspectRatio="none",
 * viewBox 1000×96) so trace x-coords are per-mille and map 1:1 onto the
 * HTML labels' percent positions; the strip is a fixed 96px tall, so
 * y-coords are honest pixels. Dots/labels/scars are HTML — circles would
 * distort under the non-uniform stretch.
 */

import type { Stage } from '../../types/events';
import type { ActiveCommission, CommissionHistoryEntry } from '../../state/slices/commission';

export interface CommissionCircuitProps {
  active: ActiveCommission | undefined;
  history: CommissionHistoryEntry[];
}

type NodeState = 'pending' | 'active' | 'passed' | 'failed';

const NODES = [
  { label: 'spec', x: 6 },
  { label: 'generate', x: 22 },
  { label: 'gate', x: 38 },
  { label: 'deploy', x: 54 },
  { label: 'test', x: 70 },
  { label: 'admit', x: 88 },
] as const;

/** Which node a stage beat lights. repair re-energizes GENERATE. */
const STAGE_NODE: Record<Stage, number> = {
  generate: 1,
  repair: 1,
  validate: 2,
  deploy: 3,
  test: 4,
};

const TRACE_Y = 30;

function deriveNodeStates(active: ActiveCommission | undefined): NodeState[] {
  const states: NodeState[] = NODES.map(() => 'pending');
  if (!active) return states;
  states[0] = 'passed'; // the human taught the spec — the one thing only a human can know
  for (const r of active.trail) {
    if (r.attempt !== active.attempt) continue; // current attempt only; scars keep the past
    const idx = STAGE_NODE[r.stage];
    states[idx] = r.status === 'started' ? 'active' : r.status;
  }
  if (active.outcome === 'passed') states[5] = 'passed';
  return states;
}

interface Scar {
  node: number;
  label: string;
  pass: boolean;
}

function deriveScars(active: ActiveCommission | undefined): Scar[] {
  if (!active) return [];
  const scars: Scar[] = [];
  for (let a = 1; a <= active.attempt; a++) {
    const failed = active.trail.filter((r) => r.attempt === a && r.status === 'failed');
    const die = failed[failed.length - 1];
    if (die) scars.push({ node: STAGE_NODE[die.stage], label: `✗${a}`, pass: false });
  }
  if (active.outcome === 'passed') {
    scars.push({ node: 5, label: `✓${active.attempt}`, pass: true });
  }
  return scars;
}

function segmentClass(downstream: NodeState): string {
  if (downstream === 'active') return 'circuit__trace circuit__trace--flow';
  if (downstream === 'passed') return 'circuit__trace circuit__trace--done';
  if (downstream === 'failed') return 'circuit__trace circuit__trace--fail';
  return 'circuit__trace';
}

export function CommissionCircuit({ active, history }: CommissionCircuitProps) {
  const states = deriveNodeStates(active);
  const scars = deriveScars(active);

  const last = active?.trail[active.trail.length - 1];
  const repairing = !!last && last.stage === 'repair' && last.status === 'started';

  const failScars = scars.filter((s) => !s.pass);
  const lastFail = failScars[failScars.length - 1];
  const returnFrom = lastFail ? lastFail.node : 4;
  const sx = NODES[returnFrom]!.x * 10;
  const gx = NODES[1].x * 10;
  const returnPath = `M ${sx} ${TRACE_Y + 4} C ${sx} 82, ${gx} 82, ${gx} ${TRACE_Y + 6}`;

  const scarsByNode = new Map<number, Scar[]>();
  for (const s of scars) {
    const list = scarsByNode.get(s.node) ?? [];
    list.push(s);
    scarsByNode.set(s.node, list);
  }

  const passedCount = history.filter((h) => h.outcome === 'passed').length;
  const failedCount = history.length - passedCount;
  const meta =
    active && !active.outcome
      ? `attempt ${active.attempt}/${active.maxAttempts}`
      : history.length > 0
        ? `${passedCount} commissioned · ${failedCount} failed`
        : 'the loop is idle';

  return (
    <div className="circuit" data-live={!!active && !active.outcome}>
      <svg
        className="circuit__svg"
        viewBox="0 0 1000 96"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {NODES.slice(0, -1).map((n, i) => {
          const next = NODES[i + 1]!;
          return (
            <line
              key={n.label}
              className={segmentClass(states[i + 1]!)}
              x1={n.x * 10 + 10}
              y1={TRACE_Y}
              x2={next.x * 10 - 10}
              y2={TRACE_Y}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
        <path
          className={`circuit__trace circuit__return${repairing ? ' circuit__return--active' : ''}`}
          d={returnPath}
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      {NODES.map((n, i) => (
        <span
          key={n.label}
          className={`circuit__dot circuit__dot--${states[i]!}`}
          style={{ left: `${n.x}%` }}
        />
      ))}
      {NODES.map((n, i) => (
        <span
          key={n.label}
          className={`circuit__label circuit__label--${states[i]!}`}
          style={{ left: `${n.x}%` }}
        >
          {n.label}
        </span>
      ))}
      {[...scarsByNode.entries()].map(([node, list]) => (
        <span className="circuit__scars" key={node} style={{ left: `${NODES[node]!.x}%` }}>
          {list.map((s) => (
            <span key={s.label} className={`circuit__scar${s.pass ? ' circuit__scar--pass' : ''}`}>
              {s.label}
            </span>
          ))}
        </span>
      ))}

      {repairing ? (
        <span
          className="circuit__repair-label"
          style={{ left: `${(NODES[1].x + NODES[returnFrom]!.x) / 2}%` }}
        >
          repair · traceback → regenerate
        </span>
      ) : null}

      <span className="circuit__meta">{meta}</span>
    </div>
  );
}
