/**
 * Commission slice — the loop's accumulated story. `trail` is the full,
 * truthful stage history (repair loop-backs included) so the stepper renders
 * what actually happened, not a linear step index.
 */

import type { ProtocolClass, Stage, StageStatus } from '../../types/events';
import type { StageRecord } from '../../types/domain';

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
  /** VERBATIM board stderr from the latest commission.traceback. */
  lastTraceback?: string | undefined;
  /** Set once commission.passed / .failed lands; kept for the final tableau. */
  outcome?: 'passed' | 'failed' | undefined;
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
