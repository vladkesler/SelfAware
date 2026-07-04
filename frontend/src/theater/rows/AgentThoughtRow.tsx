/** AgentThoughtRow — the model reasoning out loud. */

import type { EventOf } from '../../types/events';
import { tsClock } from './RawEventRow';

export function AgentThoughtRow({ event }: { event: EventOf<'agent.thought'> }) {
  const { agent, text } = event.payload;
  return (
    <div className="row machine row--thought">
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">{agent}</span>
      <span className="row__thought">“{text}”</span>
    </div>
  );
}
