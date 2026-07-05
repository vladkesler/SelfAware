/**
 * Chat slice — copilot conversation. `streaming` accumulates agent.message
 * deltas until done:true folds them into a ChatMessage. `tools` is the
 * copilot's tool-call ledger (agent.tool_call → agent.tool_result), rendered
 * as inline chips in the transcript.
 */

import type { ChatMessage, ChatToolEntry } from '../../types/domain';

export interface ChatSlice {
  messages: ChatMessage[];
  streaming?: string | undefined;
  tools: ChatToolEntry[];
}

export function initialChat(): ChatSlice {
  return { messages: [], tools: [] };
}
