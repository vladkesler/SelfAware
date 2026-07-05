/**
 * ToolChip — one agent tool call, rendered live: it appears in-flight (charge
 * left-border) the instant agent.tool_call lands, then resolves to ok
 * (live-orange) or err (alert) when agent.tool_result patches it. Shared by the
 * AGENT column (AUTHOR/MEDIC dry_gate) and the PILOT console (read_/set_) so
 * every agent shows the hands it is using — the judge-facing proof of work.
 */

import type { ChatToolEntry } from '../../types/domain';

function compactArgs(args: Record<string, unknown>): string {
  const s = Object.entries(args)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? `"${v}"` : String(v)}`)
    .join(', ');
  return s.length > 48 ? `${s.slice(0, 48)}…` : s;
}

export function ToolChip({ entry }: { entry: ChatToolEntry }) {
  const state = entry.ok === undefined ? 'pending' : entry.ok ? 'ok' : 'err';
  return (
    <span className="toolchip machine" data-state={state}>
      <span className="toolchip__call">
        {entry.tool}
        <span className="toolchip__args">({compactArgs(entry.args)})</span>
      </span>
      {entry.preview !== undefined ? (
        <span className="toolchip__result">→ {entry.preview}</span>
      ) : (
        <span className="toolchip__spin" aria-hidden>
          ⋯
        </span>
      )}
    </span>
  );
}
