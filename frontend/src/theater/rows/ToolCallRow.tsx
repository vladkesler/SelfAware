/** ToolCallRow — agent tool invocation, args inline. */

import type { EventOf } from '../../types/events';
import { tsClock } from './RawEventRow';

export function ToolCallRow({ event }: { event: EventOf<'agent.tool_call'> }) {
  const { agent, tool, args } = event.payload;
  return (
    <div className="row machine">
      <span className="row__ts">{tsClock(event.ts)}</span>
      <span className="row__type">{agent}</span>
      <span>
        ⚙ {tool}({JSON.stringify(args)})
      </span>
    </div>
  );
}
