/**
 * PilotConsole — the PILOT at work, and the place you talk to it. The drivers
 * AUTHOR and MEDIC just built are PILOT's tools: "what's the temperature?" →
 * it calls read_shtc3 live; "set the servo to halfway" → set_servo. Tool calls
 * render as live chips (in-flight → resolved) so judges watch the hands, not
 * just the words. Enter sends — the machine's idiom.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ChatMessage, ChatToolEntry } from '../types/domain';
import { ToolChip } from '../components/primitives/ToolChip';

export interface PilotConsoleProps {
  messages: ChatMessage[];
  streaming?: string | undefined;
  tools: ChatToolEntry[];
  /** Every armed tool name, from the registry (grows on admission). */
  toolNames: string[];
  disabled: boolean;
  fixtureMode: boolean;
  onSend: (text: string) => void;
}

const PROMPT_CHIPS = [
  "what's the temperature right now?",
  'set the servo to halfway, then back to rest',
  'what tools do you have?',
];

type Entry =
  | { kind: 'msg'; at: string; idx: number; msg: ChatMessage }
  | { kind: 'tool'; at: string; idx: number; tool: ChatToolEntry };

export function PilotConsole({
  messages,
  streaming,
  tools,
  toolNames,
  disabled,
  fixtureMode,
  onSend,
}: PilotConsoleProps) {
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
    <div className="pilot">
      <div className="pilot__toolbelt machine">
        <span className="pilot__toolbelt-label">armed tools</span>
        {toolNames.length === 0 ? (
          <span className="pilot__notools">none yet — commission a part</span>
        ) : (
          toolNames.map((t) => (
            <span key={t} className="chip chip--fresh">
              {t}
            </span>
          ))
        )}
      </div>

      <div className="pilot__log" ref={logRef}>
        {entries.length === 0 && !streaming ? (
          <div className="pilot__empty machine">
            ask the pilot to read a sensor or drive an actuator — it answers with its hands
          </div>
        ) : null}
        {entries.map((e) =>
          e.kind === 'msg' ? (
            <div key={`m${e.idx}`} className={`pilot__msg pilot__msg--${e.msg.role}`}>
              <span className="pilot__who machine">{e.msg.role === 'user' ? 'you' : '◇ pilot'}</span>
              <span className="pilot__text">{e.msg.text}</span>
            </div>
          ) : (
            <div key={`t${e.tool.id}`} className="pilot__toolrow">
              <ToolChip entry={e.tool} />
            </div>
          ),
        )}
        {streaming !== undefined ? (
          <div className="pilot__msg pilot__msg--agent">
            <span className="pilot__who machine">◇ pilot</span>
            <span className="pilot__text">
              {streaming}
              <span className="pilot__cursor">▌</span>
            </span>
          </div>
        ) : null}
      </div>

      <div className="pilot__prompts">
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

      <form className="pilot__form" onSubmit={submit}>
        <span className="pilot__prompt machine">&gt;</span>
        <input
          className="input machine"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            fixtureMode
              ? 'fixture replay — pilot offline'
              : disabled
                ? 'link down — reconnecting'
                : 'ask the pilot…'
          }
          disabled={inputDisabled}
        />
      </form>
    </div>
  );
}
