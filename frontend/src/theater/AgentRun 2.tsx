/**
 * AgentRun — the active agent's mind, live. One beat per (attempt, stage):
 * ⟨glyph⟩ PERSONA · action · result. The agent's reasoning types out under its
 * own beat; the tools it calls (AUTHOR/MEDIC → dry_gate) render as live chips
 * right there; the BOARD's VERBATIM traceback shows under the beat that raised
 * it. This is the judge-facing "watch it work" surface — thinking + hands, in
 * one honest stream.
 */

import { useEffect, useRef } from 'react';
import type { ActiveCommission } from '../state/slices/commission';
import { MachineText } from '../components/primitives/MachineText';
import { ToolChip } from '../components/primitives/ToolChip';
import { PERSONAS } from './agents';
import { describeStep, foldTrail, type RunStep } from './actors';

function Traceback({ text }: { text: string }) {
  const lines = text.replace(/\n$/, '').split('\n');
  return (
    <div className="runstep__traceback">
      {lines.map((l, i) => (
        <pre
          key={i}
          className={`term__line term__line--stderr${
            i === lines.length - 1 ? ' term__line--exception' : ''
          }`}
        >
          {l || ' '}
        </pre>
      ))}
    </div>
  );
}

export function AgentRun({ active }: { active: ActiveCommission }) {
  const steps = foldTrail(active).map((r) => describeStep(r, active));
  const liveIdx = active.outcome ? -1 : steps.length - 1;

  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (pinnedRef.current) el.scrollTop = el.scrollHeight;
    };
    raf = requestAnimationFrame(loop);
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) pinnedRef.current = false;
    };
    el.addEventListener('wheel', onWheel, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener('wheel', onWheel);
    };
  }, []);
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 32) pinnedRef.current = true;
  };

  const admitted = active.outcome === 'passed';
  const failed = active.outcome === 'failed';

  return (
    <div className="agentrun" ref={scrollRef} onScroll={onScroll}>
      {steps.map((s, i) => (
        <Step
          key={`${s.attempt}:${s.stage}`}
          step={s}
          active={active}
          live={i === liveIdx}
          newAttempt={i > 0 && s.attempt !== steps[i - 1]!.attempt}
        />
      ))}

      {admitted ? (
        <div className="runstep runstep--admit">
          <span className="runstep__actor">{PERSONAS.host.label}</span>
          <span className="runstep__action">admitted → registry</span>
          <span className="runstep__result runstep__result--live">read_{active.slug} armed</span>
        </div>
      ) : null}
      {failed ? (
        <div className="runstep runstep--fail">
          <span className="runstep__actor">{PERSONAS.board.label}</span>
          <span className="runstep__action">the board never vouched — not admitted</span>
          <span className="runstep__result runstep__result--alert">✗</span>
        </div>
      ) : null}
    </div>
  );
}

function Step({
  step,
  active,
  live,
  newAttempt,
}: {
  step: RunStep;
  active: ActiveCommission;
  live: boolean;
  newAttempt: boolean;
}) {
  const persona = PERSONAS[step.actor];
  const isAuthoring = step.actor === 'author' || step.actor === 'medic';
  const reasoning = isAuthoring ? active.thoughtsByAttempt[step.attempt] : undefined;
  const tools = isAuthoring ? active.toolsByAttempt[step.attempt] : undefined;
  const traceback =
    step.actor === 'board' && step.status === 'failed'
      ? active.tracebackByAttempt[step.attempt]
      : undefined;

  return (
    <>
      {newAttempt ? <div className="agentrun__divider">attempt {step.attempt}</div> : null}
      <div className={`runstep${live ? ' runstep--live' : ''}`} data-actor={step.actor}>
        <span className="runstep__actor">
          <span className="runstep__glyph">{persona.glyph}</span> {persona.label}
        </span>
        <span className="runstep__action">{step.action}</span>
        <span className={`runstep__result runstep__result--${step.tone}`}>{step.result}</span>
      </div>
      {step.detail ? <div className="runstep__detail">{step.detail}</div> : null}
      {reasoning && reasoning.length > 0 ? (
        <div className="runstep__reason">
          <MachineText text={reasoning.join(' ')} typewriter={live && !active.outcome} charMs={12} />
        </div>
      ) : null}
      {tools && tools.length > 0 ? (
        <div className="runstep__tools">
          {tools.map((t) => (
            <ToolChip key={t.id} entry={t} />
          ))}
        </div>
      ) : null}
      {traceback ? <Traceback text={traceback} /> : null}
    </>
  );
}
