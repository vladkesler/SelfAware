/**
 * ChatDock — talk to the copilot. Streams agent.message deltas via
 * chat.streaming; input is disabled while the transport is disconnected.
 */

import { useState } from 'react';
import type { FormEvent } from 'react';
import type { ChatMessage } from '../../types/domain';

export interface ChatDockProps {
  messages: ChatMessage[];
  streaming?: string | undefined;
  disabled: boolean;
  onSend: (text: string) => void;
}

export function ChatDock({ messages, streaming, disabled, onSend }: ChatDockProps) {
  const [draft, setDraft] = useState('');

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft('');
  };

  return (
    <div className="chat">
      <div className="chat__log">
        {messages.length === 0 && !streaming ? (
          <div className="chat__empty machine">ask the copilot — “commission the LDR on GP27”</div>
        ) : null}
        {messages.map((m, i) => (
          <div key={i} className={`chat__msg chat__msg--${m.role}`}>
            <span className="chat__who machine">{m.role === 'user' ? '>' : 'copilot'}</span>
            <span className="chat__text">{m.text}</span>
          </div>
        ))}
        {streaming !== undefined ? (
          <div className="chat__msg chat__msg--agent">
            <span className="chat__who machine">copilot</span>
            <span className="chat__text">
              {streaming}
              <span className="term__cursor">▌</span>
            </span>
          </div>
        ) : null}
      </div>
      <form className="chat__form" onSubmit={submit}>
        <span className="chat__prompt machine">&gt;</span>
        <input
          className="input machine"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={disabled ? 'disconnected' : 'talk to the machine…'}
          disabled={disabled}
        />
        <button type="submit" className="btn" disabled={disabled || !draft.trim()}>
          send
        </button>
      </form>
    </div>
  );
}
