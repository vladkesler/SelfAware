/**
 * applyEvent — THE exhaustive switch mapping server events onto slices.
 *
 * Rules:
 *  - EVERY event (known or unknown) is pushed into the feed ring first.
 *  - Unknown event types skip the switch entirely (feed-only, never an error).
 *  - The switch covers every ServerEvent['type']; the default arm is a
 *    `never` exhaustiveness check, so adding an event type without a case
 *    fails typecheck here.
 *  - After state, presentation: the theater registry names which panel
 *    pulses for this event type (plus explicit ui.panel pulse hints).
 */

import type { AnyEvent, DriverSummary } from '../types/events';
import { isKnownEvent } from '../types/events';
import type { DriverCard, PresenceCard, ReadingPoint, StageRecord } from '../types/domain';
import { RingBuffer } from '../lib/ring';
import { READINGS_CAP } from './slices/readings';
import { presenceKey } from './slices/drivers';
import { resolvePulse } from '../theater/registry';
import { firePulse } from '../theater/pulse';
import type { StoreGet, StoreSet } from './store';

function summaryToCard(d: DriverSummary): DriverCard {
  return {
    slug: d.slug,
    displayName: d.display_name,
    protocolClass: d.protocol_class,
    pins: {}, // hello's DriverSummary is thin; driver.registered fills these
    toolNames: [],
    codeHash: '',
    unit: d.unit,
    status: d.status === 'active' ? 'live' : 'repairing',
    ...(d.last_reading !== null ? { lastReading: d.last_reading } : {}),
  };
}

export function applyEvent(ev: AnyEvent, set: StoreSet, get: StoreGet): void {
  // 1) Feed: the ring is mutated in place; replacing the slice object gives
  //    zustand subscribers a fresh reference per event.
  const feedEvents = get().feed.events;
  feedEvents.push(ev);

  const prevSeq = get().connection.lastSeq;
  if (prevSeq > 0 && ev.seq > prevSeq + 1) {
    console.info(`[events] seq gap ${prevSeq} → ${ev.seq} (legal: drop-oldest upstream)`);
  }
  set((s) => ({
    feed: { events: feedEvents },
    connection: { ...s.connection, lastSeq: Math.max(s.connection.lastSeq, ev.seq) },
  }));

  // 2) Unknown types land in the feed only — raw but visible, never dropped.
  if (!isKnownEvent(ev)) return;

  switch (ev.type) {
    case 'system.hello': {
      const p = ev.payload;
      const bySlug: Record<string, DriverCard> = {};
      const order: string[] = [];
      for (const d of p.drivers) {
        bySlug[d.slug] = summaryToCard(d);
        order.push(d.slug);
      }
      set((s) => ({
        connection: { ...s.connection, server: p },
        board: {
          connected: p.board.connected,
          portId: p.board.port_id,
          mock: p.board.mock,
          busy: p.board.busy,
        },
        // hello restates full state → replace drivers; presences are ephemeral
        drivers: { ...s.drivers, bySlug, order },
      }));
      break;
    }

    case 'system.ack':
      break; // feed row is the receipt; command tracking is build-day

    case 'system.error':
      break; // surfaced via the feed (RawEventRow); toast UX is build-day

    case 'board.connected': {
      const p = ev.payload;
      set((s) => ({ board: { ...s.board, connected: true, portId: p.port_id, mock: p.mock } }));
      break;
    }

    case 'board.disconnected': {
      set((s) => ({ board: { ...s.board, connected: false, busy: false } }));
      break;
    }

    case 'board.status': {
      const p = ev.payload;
      set(() => ({
        board: { connected: p.connected, portId: p.port_id, mock: p.mock, busy: p.busy },
      }));
      break;
    }

    case 'commission.started': {
      const p = ev.payload;
      set((s) => ({
        commission: {
          ...s.commission,
          active: {
            id: p.commission_id,
            slug: p.slug,
            displayName: p.display_name,
            protocolClass: p.protocol_class,
            attempt: 1,
            maxAttempts: p.max_attempts,
            trail: [],
          },
        },
      }));
      break;
    }

    case 'commission.stage': {
      const p = ev.payload;
      set((s) => {
        const a = s.commission.active;
        if (!a || a.id !== p.commission_id) return {};
        const rec: StageRecord = {
          stage: p.stage,
          status: p.status,
          attempt: p.attempt,
          at: ev.ts,
          ...(p.detail ? { detail: p.detail } : {}),
        };
        return {
          commission: {
            ...s.commission,
            active: {
              ...a,
              attempt: p.attempt,
              stage: p.stage,
              stageStatus: p.status,
              trail: [...a.trail, rec],
            },
          },
        };
      });
      break;
    }

    case 'commission.traceback': {
      const p = ev.payload;
      set((s) => {
        const a = s.commission.active;
        if (!a || a.id !== p.commission_id) return {};
        return {
          commission: { ...s.commission, active: { ...a, lastTraceback: p.traceback } },
        };
      });
      break;
    }

    case 'commission.passed': {
      const p = ev.payload;
      set((s) => {
        const a = s.commission.active;
        return {
          commission: {
            // keep the finished trail on stage for the final tableau
            active:
              a && a.id === p.commission_id
                ? { ...a, outcome: 'passed', stage: undefined, stageStatus: undefined }
                : a,
            history: [
              ...s.commission.history,
              { slug: p.slug, outcome: 'passed', attempts: p.attempts_used, at: ev.ts },
            ],
          },
        };
      });
      break;
    }

    case 'commission.failed': {
      const p = ev.payload;
      set((s) => {
        const a = s.commission.active;
        return {
          commission: {
            active:
              a && a.id === p.commission_id
                ? {
                    ...a,
                    outcome: 'failed',
                    stage: undefined,
                    stageStatus: undefined,
                    ...(p.last_traceback ? { lastTraceback: p.last_traceback } : {}),
                  }
                : a,
            history: [
              ...s.commission.history,
              { slug: p.slug, outcome: 'failed', attempts: p.attempts_used, at: ev.ts },
            ],
          },
        };
      });
      break;
    }

    case 'agent.thought':
    case 'agent.tool_call':
    case 'agent.tool_result':
      break; // theater rows carry these; no accumulated state yet

    case 'agent.message': {
      const p = ev.payload;
      set((s) => {
        const acc = (s.chat.streaming ?? '') + p.delta;
        if (p.done) {
          return {
            chat: {
              messages: [...s.chat.messages, { role: 'agent', text: acc, at: ev.ts }],
              streaming: undefined,
            },
          };
        }
        return { chat: { ...s.chat, streaming: acc } };
      });
      break;
    }

    case 'sensor.reading': {
      const p = ev.payload;
      const state = get();
      let ring = state.readings.bySlug[p.slug];
      let bySlug = state.readings.bySlug;
      if (!ring) {
        ring = new RingBuffer<ReadingPoint>(READINGS_CAP);
        bySlug = { ...bySlug, [p.slug]: ring };
      }
      // HOT PATH: ring mutated in place; only the version counter is immutable.
      ring.push({ t: Date.now(), v: p.value, plausible: p.plausible });
      set((s) => {
        const card = s.drivers.bySlug[p.slug];
        return {
          readings: {
            bySlug,
            version: { ...s.readings.version, [p.slug]: (s.readings.version[p.slug] ?? 0) + 1 },
          },
          ...(card
            ? {
                drivers: {
                  ...s.drivers,
                  bySlug: { ...s.drivers.bySlug, [p.slug]: { ...card, lastReading: p.value } },
                },
              }
            : {}),
        };
      });
      break;
    }

    case 'actuator.state': {
      const p = ev.payload;
      set((s) => {
        const card = s.drivers.bySlug[p.slug];
        if (!card) return {};
        return {
          drivers: {
            ...s.drivers,
            bySlug: { ...s.drivers.bySlug, [p.slug]: { ...card, lastReading: p.level } },
          },
        };
      });
      break;
    }

    case 'discovery.device_found': {
      const p = ev.payload;
      const key = presenceKey(p.bus, p.addr, p.pin);
      const card: PresenceCard = {
        key,
        bus: p.bus,
        confidence: p.confidence,
        ...(p.addr != null ? { addr: p.addr } : {}),
        ...(p.pin != null ? { pin: p.pin } : {}),
        ...(p.identity ? { identity: p.identity } : {}),
        ...(p.suggested_spec ? { suggestedSpec: p.suggested_spec } : {}),
      };
      set((s) => ({
        drivers: { ...s.drivers, presences: { ...s.drivers.presences, [key]: card } },
      }));
      break;
    }

    case 'discovery.device_lost': {
      const p = ev.payload;
      const key = presenceKey(p.bus, p.addr, p.pin);
      set((s) => {
        if (!(key in s.drivers.presences)) return {};
        const presences = { ...s.drivers.presences };
        delete presences[key];
        return { drivers: { ...s.drivers, presences } };
      });
      break;
    }

    case 'driver.registered': {
      const p = ev.payload;
      const card: DriverCard = {
        slug: p.slug,
        displayName: p.display_name,
        protocolClass: p.protocol_class,
        pins: p.pins,
        toolNames: p.tool_names,
        codeHash: p.code_hash,
        unit: p.unit,
        status: 'live',
      };
      set((s) => {
        // a registered driver resolves its ADC presence card, if any
        const presences = { ...s.drivers.presences };
        for (const pin of Object.values(p.pins)) delete presences[`adc:${pin}`];
        return {
          drivers: {
            bySlug: { ...s.drivers.bySlug, [p.slug]: card },
            presences,
            order: s.drivers.order.includes(p.slug)
              ? s.drivers.order
              : [...s.drivers.order, p.slug],
          },
        };
      });
      break;
    }

    case 'driver.updated': {
      const p = ev.payload;
      set((s) => {
        const card = s.drivers.bySlug[p.slug];
        if (!card) return {};
        return {
          drivers: {
            ...s.drivers,
            bySlug: {
              ...s.drivers.bySlug,
              [p.slug]: { ...card, codeHash: p.code_hash, status: 'live' },
            },
          },
        };
      });
      break;
    }

    case 'ui.panel': {
      const p = ev.payload;
      if (p.hint === 'pulse') firePulse(p.target);
      // 'focus' (center-stage swap) is a reserved mechanism — build day
      break;
    }

    default: {
      // Exhaustiveness: a new ServerEvent member without a case fails HERE.
      const unhandled: never = ev;
      void unhandled;
    }
  }

  // 3) Presentation pulse via the theater registry.
  const pulse = resolvePulse(ev.type);
  if (pulse) firePulse(pulse);
}
