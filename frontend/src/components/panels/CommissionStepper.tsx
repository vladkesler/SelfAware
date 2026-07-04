/**
 * CommissionStepper — the loop as a live pipeline. The four forward stages
 * light up from the truthful `trail` (latest record per stage wins); repair
 * renders as a loop-back marker under the pipeline, counting the retries.
 * Placeholder visuals; the craft pass is build-day.
 */

import type { ProtocolClass, Stage, StageStatus } from '../../types/events';
import type { StageRecord } from '../../types/domain';

export interface CommissionStepperProps {
  slug?: string | undefined;
  protocolClass?: ProtocolClass | undefined;
  attempt: number;
  maxAttempts: number;
  trail: StageRecord[];
  activeStage?: Stage | undefined;
  activeStatus?: StageStatus | undefined;
  outcome?: 'passed' | 'failed' | undefined;
}

const PIPELINE: readonly Stage[] = ['generate', 'validate', 'deploy', 'test'];

function stageState(
  stage: Stage,
  trail: StageRecord[],
  activeStage: Stage | undefined,
): 'passed' | 'failed' | 'active' | 'pending' {
  let latest: StageRecord | undefined;
  for (const r of trail) if (r.stage === stage) latest = r; // last record wins
  if (activeStage === stage && latest?.status === 'started') return 'active';
  if (latest?.status === 'passed') return 'passed';
  if (latest?.status === 'failed') return 'failed';
  if (latest?.status === 'started') return 'active';
  return 'pending';
}

export function CommissionStepper({
  slug,
  protocolClass,
  attempt,
  maxAttempts,
  trail,
  activeStage,
  activeStatus,
  outcome,
}: CommissionStepperProps) {
  if (!slug) {
    return (
      <div className="stepper stepper--empty machine">
        no commission in flight — plug something in, or ask the copilot
      </div>
    );
  }

  const repairs = trail.filter((r) => r.stage === 'repair' && r.status === 'started').length;
  const repairing = activeStage === 'repair' && activeStatus === 'started';

  return (
    <div className="stepper machine">
      <div className="stepper__head">
        <span className="stepper__slug">{slug}</span>
        <span className="stepper__class">{protocolClass}</span>
        <span className="stepper__attempt">
          attempt {attempt}/{maxAttempts}
        </span>
        {outcome ? (
          <span className={`stepper__outcome stepper__outcome--${outcome}`}>
            {outcome === 'passed' ? '✓ commissioned' : '✗ failed'}
          </span>
        ) : null}
      </div>

      <div className="stepper__pipeline">
        {PIPELINE.map((stage, i) => {
          const state = stageState(stage, trail, activeStage);
          return (
            <span key={stage} className="stepper__step">
              {i > 0 ? <span className="stepper__arrow">→</span> : null}
              <span className={`stage stage--${state}`}>{stage}</span>
            </span>
          );
        })}
      </div>

      <div
        className={`stepper__loopback${repairs > 0 ? ' stepper__loopback--lit' : ''}${
          repairing ? ' stepper__loopback--active' : ''
        }`}
      >
        ↺ repair{repairs > 0 ? ` ×${repairs}` : ''}
        <span className="stepper__loopnote">
          {repairing ? ' — feeding the traceback back' : ' (traceback → regenerate)'}
        </span>
      </div>
    </div>
  );
}
