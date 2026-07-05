/**
 * Commission slice — the loop's accumulated story. `trail` is the full,
 * truthful stage history (repair loop-backs included) so the stepper renders
 * what actually happened, not a linear step index.
 */

import type { ProtocolClass, Stage, StageStatus } from '../../types/events';
import type { ChatToolEntry, StageRecord } from '../../types/domain';

export interface AttemptCode {
  code: string;
  isRepair: boolean;
}

export interface ActiveCommission {
  id: string;
  slug: string;
  displayName: string;
  protocolClass: ProtocolClass;
  attempt: number;
  maxAttempts: number;
  stage?: Stage | undefined;
  stageStatus?: StageStatus | undefined;
  trail: StageRecord[];
  /** Generated driver source per attempt (commission.code) — failed attempts included. */
  codeByAttempt: Record<number, AttemptCode>;
  /** AUTHOR (attempt 1) / MEDIC (repairs) reasoning per attempt (agent.thought). */
  thoughtsByAttempt: Record<number, string[]>;
  /** Tools the agent called per attempt (agent.tool_call/result — e.g. dry_gate). */
  toolsByAttempt: Record<number, ChatToolEntry[]>;
  /** VERBATIM board stderr per attempt (commission.traceback). */
  tracebackByAttempt: Record<number, string>;
  /** VERBATIM board stderr from the latest commission.traceback. */
  lastTraceback?: string | undefined;
  /** Set once commission.passed / .failed lands; kept for the final tableau. */
  outcome?: 'passed' | 'failed' | undefined;
  /** From commission.passed — the verdict tableau's hero figures. */
  finalReading?: number | null | undefined;
  finalUnit?: string | undefined;
  /** From commission.failed — the honest reason. */
  failReason?: string | undefined;
}

export interface CommissionHistoryEntry {
  slug: string;
  outcome: 'passed' | 'failed';
  attempts: number;
  at: string;
}

export interface CommissionSlice {
  active?: ActiveCommission | undefined;
  history: CommissionHistoryEntry[];
}

export function initialCommission(): CommissionSlice {
  return { history: [] };
}
