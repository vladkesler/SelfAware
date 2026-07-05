/**
 * actors — the commission as a persona-labeled play-by-play. Each trail record
 * folds to exactly one beat: one persona doing one thing with one result.
 * AUTHOR writes (generate); MEDIC repairs (repair); the HOST gates + deploys;
 * the BOARD runs it and is the arbiter of truth. No invented tool calls — the
 * only real tool the driver agents use (dry_gate) arrives as agent.tool_call.
 */

import type { StageRecord } from '../types/domain';
import type { ActiveCommission } from '../state/slices/commission';
import type { AgentKey } from './agents';

export type StepTone = 'charge' | 'live' | 'alert';

export interface RunStep {
  actor: AgentKey;
  action: string;
  result: string;
  /** A longer reason (gate rejection, plausibility verdict) — its own sub-line. */
  detail?: string;
  tone: StepTone;
  attempt: number;
  stage: StageRecord['stage'];
  status: StageRecord['status'];
}

function readingOf(detail: string | undefined): string | null {
  const m = detail?.match(/reading=([-\d.]+)/);
  return m ? m[1]! : null;
}

/** One trail record → one persona beat. */
export function describeStep(r: StageRecord, active: ActiveCommission): RunStep {
  const running = r.status === 'started';
  const failed = r.status === 'failed';
  const tone: StepTone = running ? 'charge' : failed ? 'alert' : 'live';
  const mark = running ? '…' : failed ? '✗' : '✓';
  const base = { attempt: r.attempt, stage: r.stage, status: r.status };

  switch (r.stage) {
    case 'generate':
      return { actor: 'author', action: 'writes the driver', result: mark, tone, ...base };
    case 'repair':
      return { actor: 'medic', action: 'reads the error, rewrites', result: mark, tone, ...base };
    case 'validate':
      return {
        actor: 'host',
        action: 'static safety gate',
        result: mark,
        ...(failed ? { detail: r.detail ?? 'rejected unsafe code' } : {}),
        tone,
        ...base,
      };
    case 'deploy':
      return { actor: 'host', action: 'deploy → board', result: mark, tone, ...base };
    case 'test': {
      if (running) return { actor: 'board', action: 'runs it', result: '…', tone: 'charge', ...base };
      if (r.status === 'passed') {
        const reading = readingOf(r.detail);
        return { actor: 'board', action: 'answered', result: reading ?? '✓', tone: 'live', ...base };
      }
      const d = r.detail ?? '';
      if (/timeout|hung|soft.?reset/i.test(d)) {
        return { actor: 'board', action: 'hung — soft reset', result: '✗', tone: 'alert', ...base };
      }
      if (active.tracebackByAttempt[r.attempt]) {
        return { actor: 'board', action: 'raised a traceback', result: '✗', tone: 'alert', ...base };
      }
      return {
        actor: 'host',
        action: 'rejected the reading',
        result: '✗',
        detail: d || 'implausible value',
        tone: 'alert',
        ...base,
      };
    }
  }
}

/** Fold the trail into one record per (attempt, stage), first-seen order. */
export function foldTrail(active: ActiveCommission): StageRecord[] {
  const seen = new Map<string, StageRecord>();
  const order: string[] = [];
  for (const r of active.trail) {
    const key = `${r.attempt}:${r.stage}`;
    if (!seen.has(key)) order.push(key);
    seen.set(key, r);
  }
  return order.map((k) => seen.get(k)!);
}
