/**
 * ChatDock — the copilot command line. A toolbelt strip shows every tool
 * the loop has manufactured (chips pop in on admission); tool calls render
 * INLINE in the transcript as chips that resolve charge → live/alert
 * with their result; pre-typed prompt chips keep the presenter off the
 * keyboard. No send button — Enter is the machine's idiom.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ChatMessage, ChatToolEntry } from '../../types/domain';

export interface ChatDockProps {
  messages: ChatMessage[];
  streaming?: string | undefined;
  tools: ChatToolEntry[];
  /** Every armed tool name, from the registry (grows on admission). */
  toolNames: string[];
  disabled: boolean;
  /** Fixture replay (?mock=1) — the copilot is not really there. */
  fixtureMode: boolean;
  onSend: (text: string) => void;
}

const PROMPT_CHIPS = [
  'what tools do you have?',
  "what's the light level right now?",
  'set the servo to halfway, then back to rest',
];

function compactArgs(args: Record<string, unknown>): string {
  const s = Object.entries(args)
    .map(([k, v]) => `${k}:${typeof v === 'string' ? `"${v}"` : String(v)}`)
    .join(', ');
  return s.length > 42 ? `${s.slice(0, 42)}…` : s;
}

type Entry =
  | { kind: 'msg'; at: string; idx: number; msg: ChatMessage }
  | { kind: 'tool'; at: string; idx: number; tool: ChatToolEntry };

export function ChatDock({
  messages,
  streaming,
  tools,
  toolNames,
  disabled,
  fixtureMode,
  onSend,
}: ChatDockProps) {
  const [draft, setDraft] = useState('');
  const logRef = useRef<HTMLDivElement>(null);

  const entries = useMemo<Entry[]>(() => {
    const all: Entry[] = [
      ...messages.map((m, idx) => ({ kind: 'msg' as const, at: m.at, idx, msg: m })),
      ...tools.map((t, idx) => ({ kind: 'tool' as const, at: t.at, idx, tool: t })),
    ];
    return all.sort((a, b) => (a.at === b.at ? a.idx - b.idx : a.at < b.at ? -1 : 1));
  }, [messages, tools]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length, streaming]);

  const inputDisabled = disabled || fixtureMode;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || inputDisabled) return;
    onSend(text);
    setDraft('');
  };

  return (
    <div className="chat">
      <div className="toolbelt">
        <span className="toolbelt__label">tools ▸</span>
        {toolNames.length === 0 ? (
          <span className="toolbelt__empty">none yet — commission something</span>
        ) : (
          toolNames.map((t) => (
            <span key={t} className="chip chip--fresh">
              {t}
            </span>
          ))
        )}
      </div>

      <div className="chat__log" ref={logRef}>
        {entries.length === 0 && !streaming ? (
          <div className="chat__empty machine">ask the machine — it answers with its hands</div>
        ) : null}
        {entries.map((e) =>
          e.kind === 'msg' ? (
            <div key={`m${e.idx}`} className={`chat__msg chat__msg--${e.msg.role}`}>
              <span className="chat__who machine">{e.msg.role === 'user' ? '>' : 'copilot'}</span>
              <span className="chat__text">{e.msg.text}</span>
            </div>
          ) : (
            <span
              key={`t${e.tool.id}`}
              className={`toolchip${
                e.tool.ok === undefined ? '' : e.tool.ok ? ' toolchip--ok' : ' toolchip--err'
              }`}
            >
              ▸ {e.tool.tool}({compactArgs(e.tool.args)})
              {e.tool.preview !== undefined ? (
                <span className="toolchip__result">→ {e.tool.preview}</span>
              ) : null}
            </span>
          ),
        )}
        {streaming !== undefined ? (
          <div className="chat__msg chat__msg--agent">
            <span className="chat__who machine">copilot</span>
            <span className="chat__text">
              {streaming}
              <span className="chat__cursor">▌</span>
            </span>
          </div>
        ) : null}
      </div>

      <div className="chat__prompts">
        {PROMPT_CHIPS.map((p) => (
          <button
            key={p}
            type="button"
            className="btn"
            disabled={inputDisabled}
            onClick={() => onSend(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <form className="chat__form" onSubmit={submit}>
        <span className="chat__prompt">&gt;</span>
        <input
          className="input machine"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            fixtureMode
              ? 'fixture replay — copilot offline'
              : disabled
                ? 'link down — reconnecting'
                : 'ask the machine…'
          }
          disabled={inputDisabled}
        />
      </form>
    </div>
  );
}
