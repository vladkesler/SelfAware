/**
 * narrate — every wire event as one human sentence for the mission log.
 * Pure function: event → { tone, text } | null (null = hidden from the log;
 * agent.message deltas would flood the ring at token rate, ui.panel is
 * plumbing). Tone tints the row's left tick, not the words — color is
 * scarce. commission.traceback is handled by its dedicated verbatim row.
 */

import type { ServerEvent } from '../types/events';
import { isCommissionAgent } from '../types/events';

export type LogTone = 'neutral' | 'live' | 'charge' | 'alert' | 'faint';

/** Where the eye should land: milestones lead, routine beats recede. */
export type LogWeight = 'milestone' | 'normal' | 'muted';

export interface Narration {
  tone: LogTone;
  text: string;
}

/**
 * Importance tier for the mission log — the fix for "I don't know where to
 * look." Milestones (the story) stay bright; routine pipeline chatter
 * (generate/deploy/gate started+passed) is muted. The center's AgentRun is
 * now the play-by-play; the log is the raw record with the milestones lifted.
 */
export function weightOf(ev: ServerEvent): LogWeight {
  switch (ev.type) {
    case 'commission.started':
    case 'commission.passed':
    case 'commission.failed':
    case 'commission.traceback':
    case 'driver.registered':
    case 'discovery.device_found':
    case 'system.error':
      return 'milestone';
    case 'agent.thought':
      return isCommissionAgent(ev.payload.agent) ? 'milestone' : 'normal';
    case 'commission.stage':
      if (ev.payload.status === 'failed') return 'milestone';
      if (ev.payload.stage === 'test' && ev.payload.status === 'passed') return 'milestone';
      return 'muted'; // routine generate/deploy/gate started+passed
    case 'board.disconnected':
      return 'milestone';
    case 'system.ack':
    case 'board.status':
    case 'board.connected':
    case 'discovery.device_lost':
      return 'muted';
    default:
      return 'normal';
  }
}

const STAGE_LABEL: Record<string, string> = {
  generate: 'generate',
  repair: 'repair',
  validate: 'gate',
  deploy: 'deploy',
  test: 'test',
};

function pins(p: Record<string, number>): string {
  return Object.entries(p)
    .map(([role, gpio]) => `${role}=GP${gpio}`)
    .join(' ');
}

function where(bus: 'i2c' | 'adc', addr?: number | null, pin?: number | null): string {
  return bus === 'i2c' ? `i2c 0x${(addr ?? 0).toString(16)}` : `GP${pin ?? '?'}`;
}

function trunc(s: string, n: number): string {
  const one = s.replace(/\s+/g, ' ').trim();
  return one.length > n ? `${one.slice(0, n)}…` : one;
}

export function narrate(ev: ServerEvent): Narration | null {
  switch (ev.type) {
    case 'system.hello': {
      const p = ev.payload;
      return {
        tone: 'neutral',
        text: `session open · protocol v${p.protocol_v} · ${p.drivers.length} driver${p.drivers.length === 1 ? '' : 's'} restored`,
      };
    }
    case 'system.ack':
      return { tone: 'faint', text: `ack ${ev.payload.cmd_id.slice(0, 8)}` };
    case 'system.error':
      return { tone: 'alert', text: `error ${ev.payload.code} — ${ev.payload.message}` };

    case 'board.connected': {
      const p = ev.payload;
      return { tone: 'live', text: `board up on ${p.port_id}${p.mock ? ' · MOCK' : ''}` };
    }
    case 'board.disconnected':
      return { tone: 'alert', text: `board lost — ${ev.payload.reason}` };
    case 'board.status': {
      const p = ev.payload;
      return {
        tone: 'faint',
        text: `board ${p.connected ? 'linked' : 'offline'} · ${p.busy ? 'busy' : 'idle'}${p.port_id ? ` · ${p.port_id}` : ''}`,
      };
    }

    case 'commission.started': {
      const p = ev.payload;
      return {
        tone: 'charge',
        text: `commission ${p.slug} · ${p.protocol_class} · ${pins(p.pins)} · max ${p.max_attempts} attempts`,
      };
    }
    case 'commission.stage': {
      const p = ev.payload;
      const glyph = p.status === 'passed' ? '✓' : p.status === 'failed' ? '✗' : '…';
      const tone: LogTone =
        p.status === 'failed' ? 'alert' : p.status === 'passed' ? 'live' : 'charge';
      return {
        tone,
        text: `attempt ${p.attempt} · ${STAGE_LABEL[p.stage] ?? p.stage} ${glyph}${p.detail ? ` — ${p.detail}` : ''}`,
      };
    }
    case 'commission.code': {
      const p = ev.payload;
      const lines = p.code.trim().split('\n').length;
      return {
        tone: 'charge',
        text: `attempt ${p.attempt} · ${p.is_repair ? 'repaired driver source' : 'driver source'} · ${lines} lines`,
      };
    }
    case 'commission.traceback':
      return null; // dedicated verbatim TracebackRow
    case 'commission.passed': {
      const p = ev.payload;
      return {
        tone: 'live',
        text: `✓ ${p.slug} commissioned · ${p.attempts_used} attempt${p.attempts_used === 1 ? '' : 's'}${
          p.reading !== null ? ` · ${p.reading}${p.unit ? ` ${p.unit}` : ''}` : ''
        }`,
      };
    }
    case 'commission.failed': {
      const p = ev.payload;
      return { tone: 'alert', text: `✗ ${p.slug} failed — ${p.reason}` };
    }

    case 'agent.thought':
      return { tone: 'faint', text: `${ev.payload.agent} ~ ${trunc(ev.payload.text, 110)}` };
    case 'agent.tool_call': {
      const p = ev.payload;
      const args = Object.entries(p.args)
        .map(([k, v]) => `${k}:${typeof v === 'string' ? `"${v}"` : String(v)}`)
        .join(', ');
      return { tone: 'charge', text: `${p.agent} ▸ ${p.tool}(${trunc(args, 40)})` };
    }
    case 'agent.tool_result': {
      const p = ev.payload;
      return {
        tone: p.ok ? 'live' : 'alert',
        text: `${p.tool} → ${trunc(p.preview, 60) || (p.ok ? 'ok' : 'failed')}`,
      };
    }
    case 'agent.message': {
      const p = ev.payload;
      if (!p.done) return null; // token deltas would flood the log
      return {
        tone: 'neutral',
        text: `${p.agent} replied${p.usage ? ` · ${p.usage.output_tokens} tok` : ''}`,
      };
    }

    case 'sensor.reading': {
      const p = ev.payload;
      return {
        tone: p.plausible ? 'live' : 'alert',
        text: `${p.slug} → ${p.value}${p.unit ? ` ${p.unit}` : ''}${p.plausible ? '' : ' ⚠ implausible'}`,
      };
    }
    case 'sensor.health': {
      const p = ev.payload;
      // actuators (not_monitored) and calibration ticks (unknown) aren't log
      // events — only a real verdict transition earns a serial line.
      if (p.status === 'not_monitored' || p.status === 'unknown') return null;
      const tone: LogTone =
        p.status === 'critical' ? 'alert' : p.status === 'degrading' ? 'charge' : 'live';
      const reason = p.reasons[0] ? ` · ${trunc(p.reasons[0], 80)}` : '';
      return { tone, text: `${p.slug} health → ${p.status}${reason}` };
    }
    case 'actuator.state': {
      const p = ev.payload;
      return {
        tone: p.ok ? 'live' : 'alert',
        text: `${p.slug} set → ${p.level}${p.ok ? '' : ' · NOT OK'}`,
      };
    }

    case 'discovery.device_found': {
      const p = ev.payload;
      return {
        tone: 'live',
        text: `found ${p.identity ?? 'something'} on ${where(p.bus, p.addr, p.pin)} · ${
          p.confidence === 'exact' ? 'known device' : 'unknown signature'
        }`,
      };
    }
    case 'discovery.device_lost': {
      const p = ev.payload;
      return { tone: 'faint', text: `lost ${where(p.bus, p.addr, p.pin)}` };
    }

    case 'driver.registered': {
      const p = ev.payload;
      return {
        tone: 'live',
        text: `+ ${p.slug} admitted · tools ${p.tool_names.join(', ')} · ${p.code_hash.slice(0, 8)}`,
      };
    }
    case 'driver.updated': {
      const p = ev.payload;
      return {
        tone: 'live',
        text: `${p.slug} re-verified · ${p.reason} · ${p.code_hash.slice(0, 8)}`,
      };
    }

    case 'ui.panel':
      return null; // presentation plumbing
  }
}
