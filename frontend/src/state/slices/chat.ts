/**
 * Chat slice — copilot conversation. `streaming` accumulates agent.message
 * deltas until done:true folds them into a ChatMessage.
 */

import type { ChatMessage } from '../../types/domain';

export interface ChatSlice {
  messages: ChatMessage[];
  streaming?: string | undefined;
}

export function initialChat(): ChatSlice {
  return { messages: [] };
}
