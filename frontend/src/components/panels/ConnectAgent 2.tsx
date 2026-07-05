/**
 * ConnectAgent — the fascia's "connect agent" popover. The board exposes a real
 * MCP server (Streamable HTTP); this hands a visitor the actual, copy-and-run
 * path to attach their own Claude Code to the running board. No theater: every
 * button copies a command/snippet that works. There is no one-click browser→
 * Claude install for a *local* HTTP server — Claude Code attaches via the
 * checked-in `.mcp.json` or the `claude mcp add` CLI — so the job here is to make
 * those two real operations one copy-click away.
 *
 * Nothing secret is copied: the MCP port carries no auth (SELFAWARE_MCP_TOKEN
 * gates only the backend and is held by the MCP process), so the client config
 * is token-free.
 */

import { useEffect, useRef, useState } from 'react';

const MCP_URL =
  (import.meta.env.VITE_MCP_URL as string | undefined) ?? 'http://127.0.0.1:8001/mcp';

const CLI = `claude mcp add --transport http selfaware ${MCP_URL}`;
const MCP_JSON = JSON.stringify(
  { mcpServers: { selfaware: { type: 'http', url: MCP_URL } } },
  null,
  2,
);

const COPIED_MS = 1500;

export function ConnectAgent() {
  const menuRef = useRef<HTMLDetailsElement>(null);
  const [copied, setCopied] = useState<string | null>(null);

  // Clear the "copied" confirmation after a beat.
  useEffect(() => {
    if (!copied) return;
    const id = setTimeout(() => setCopied(null), COPIED_MS);
    return () => clearTimeout(id);
  }, [copied]);

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard?.writeText(text);
      setCopied(key);
    } catch {
      // Clipboard unavailable (insecure context / denied): the text stays
      // visible and selectable below, so it can still be copied by hand.
    }
  };

  return (
    <details className="fascia__cmd connect" ref={menuRef}>
      <summary className="fascia__cmd-btn">connect agent ▸</summary>
      <div className="fascia__cmd-menu connect__menu">
        <div className="fascia__cmd-label">attach any agent over MCP</div>

        <div className="connect__block">
          <code className="connect__code">{CLI}</code>
          <button
            type="button"
            className={`btn${copied === 'cli' ? ' connect__copied' : ''}`}
            onClick={() => copy('cli', CLI)}
          >
            {copied === 'cli' ? 'copied ✓' : 'copy'}
          </button>
        </div>

        <div className="connect__block">
          <code className="connect__code connect__code--json">{MCP_JSON}</code>
          <button
            type="button"
            className={`btn${copied === 'json' ? ' connect__copied' : ''}`}
            onClick={() => copy('json', MCP_JSON)}
          >
            {copied === 'json' ? 'copied ✓' : 'copy .mcp.json'}
          </button>
        </div>

        <ol className="connect__steps">
          <li>
            <span className="machine">make dev-mcp</span> — start the MCP bridge (backend
            already running).
          </li>
          <li>
            In the repo, run <span className="machine">claude</span> (auto-loads{' '}
            <span className="machine">.mcp.json</span>, approve once). Outside the repo, paste
            the command above.
          </li>
          <li>
            Ask the agent <em>“what hardware can you reach?”</em> → it calls{' '}
            <span className="machine">list_capabilities</span>.
          </li>
        </ol>
      </div>
    </details>
  );
}
