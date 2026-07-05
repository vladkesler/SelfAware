/**
 * FixturePlayer — replays a recorded event script as if a backend were
 * narrating live. Fixtures store events WITHOUT seq/ts; both are stamped at
 * play time (seq monotonic per player, ts = now) so panels see realistic
 * envelopes. Powers `?mock=1` and the landing teaser.
 *
 * Presenter affordances (fallback-demo mode):
 * - `hold: true` (`?mock=1&hold=1`): start() arms the player but playback
 *   waits for one keypress or click anywhere — pre-stage the tab silently.
 * - Post-script liveness: once the script is exhausted, synthetic "ldr"
 *   sensor.reading events keep flowing at 1 Hz so the scope never freezes
 *   during Q&A.
 * - Pressing "." restarts the replay from entry 0 (ignored while typing in
 *   an input/textarea). seq stays monotonic across restarts — the protocol's
 *   monotonic-seq invariant holds and the frontend rehydrates on system.hello.
 *
 * send(): skeleton behavior — log the command and emit a system.ack for its
 * id. Build day: branch on cmd.type into scripted response sequences.
 */

import type { AnyEvent, ClientCommand, ServerEvent } from '../types/events';
import type { WsStatus } from './ws';
import type { EventTransport } from './transport';

type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

/** A ServerEvent minus the envelope fields stamped at play time. */
export type FixtureEvent = DistributiveOmit<ServerEvent, 'seq' | 'ts'>;

export interface FixtureEntry {
  /** Delay since the previous entry, in ms (scaled by opts.speed). */
  afterMs: number;
  event: FixtureEvent;
}

export interface FixturePlayerOpts {
  onEvent: (ev: AnyEvent) => void;
  onStatus?: ((s: WsStatus) => void) | undefined;
  loop?: boolean | undefined;
  /** Playback multiplier: 2 = twice as fast. Default 1. */
  speed?: number | undefined;
  /** Arm on start() but wait for a single keypress/click before playing. */
  hold?: boolean | undefined;
}

/** Cadence of the synthetic post-script sensor stream. */
const LIVENESS_PERIOD_MS = 1000;
const LIVENESS_SLUG = 'ldr';

export class FixturePlayer implements EventTransport {
  private seq = 0; // never reset — monotonic across loops AND "." restarts
  private index = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private liveTimer: ReturnType<typeof setInterval> | undefined;
  private liveTick = 0;
  private running = false;
  private armed = false;
  private lastLdr: { value: number; unit: string } | undefined;

  constructor(
    private readonly script: FixtureEntry[],
    private readonly opts: FixturePlayerOpts,
  ) {}

  start(): void {
    if (this.running) return;
    this.running = true;
    this.index = 0;
    this.opts.onStatus?.('open');
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', this.handleRestartKey);
    }
    if (this.opts.hold && typeof window !== 'undefined') {
      // Armed: the show begins on the presenter's first keypress or click.
      this.armed = true;
      window.addEventListener('keydown', this.releaseHold);
      window.addEventListener('click', this.releaseHold);
    } else {
      this.scheduleNext();
    }
  }

  stop(): void {
    this.running = false;
    this.armed = false;
    clearTimeout(this.timer);
    this.timer = undefined;
    this.stopLiveness();
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', this.handleRestartKey);
      window.removeEventListener('keydown', this.releaseHold);
      window.removeEventListener('click', this.releaseHold);
    }
    this.opts.onStatus?.('closed');
  }

  send(cmd: ClientCommand): boolean {
    console.info('[fixture] command (mock mode, acked but not executed):', cmd.type, cmd.payload);
    // Ack asynchronously, like a real backend would.
    setTimeout(() => {
      if (!this.running) return;
      this.emit({
        v: 1,
        type: 'system.ack',
        payload: { cmd_id: cmd.id },
      } as FixtureEvent);
    }, 30);
    return true;
  }

  /** One-shot: first keypress/click releases a held start(). */
  private readonly releaseHold = (): void => {
    if (!this.armed) return;
    this.armed = false;
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', this.releaseHold);
      window.removeEventListener('click', this.releaseHold);
    }
    this.scheduleNext();
  };

  /** "." restarts the replay from entry 0 (seq keeps climbing). */
  private readonly handleRestartKey = (ev: KeyboardEvent): void => {
    if (ev.key !== '.') return;
    if (!this.running || this.armed) return; // releaseHold owns the first key
    if (typeof document !== 'undefined') {
      const el = document.activeElement as HTMLElement | null;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) {
        return; // presenter is typing, not steering the replay
      }
    }
    this.restart();
  };

  private restart(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.stopLiveness();
    this.index = 0; // seq intentionally NOT reset — monotonic-seq invariant;
    this.scheduleNext(); // frontend rehydrates on the replayed system.hello
  }

  private scheduleNext(): void {
    if (!this.running) return;
    if (this.index >= this.script.length) {
      if (this.opts.loop) {
        this.index = 0; // seq keeps climbing across loops — gaps/monotonicity stay honest
      } else {
        this.startLiveness(); // script done — keep the scope alive for Q&A
        return;
      }
    }
    const entry = this.script[this.index]!;
    const speed = this.opts.speed && this.opts.speed > 0 ? this.opts.speed : 1;
    this.timer = setTimeout(() => {
      if (!this.running) return;
      this.index += 1;
      const ev = entry.event;
      if (ev.type === 'sensor.reading' && ev.payload.slug === LIVENESS_SLUG) {
        this.lastLdr = { value: ev.payload.value, unit: ev.payload.unit };
      }
      this.emit(ev);
      this.scheduleNext();
    }, entry.afterMs / speed);
  }

  /** Post-script: synthetic ldr readings at 1 Hz, forever, until stop/restart. */
  private startLiveness(): void {
    if (this.liveTimer !== undefined) return;
    const base = this.lastLdr ?? this.lastScriptedLdr();
    this.liveTick = 0;
    this.liveTimer = setInterval(() => {
      if (!this.running) return;
      this.liveTick += 1;
      const value = Math.round(
        base.value + Math.sin(this.liveTick * 0.35) * 420 + (Math.random() - 0.5) * 240,
      );
      this.emit({
        v: 1,
        type: 'sensor.reading',
        payload: { slug: LIVENESS_SLUG, value, unit: base.unit, plausible: true },
      });
    }, LIVENESS_PERIOD_MS);
  }

  private stopLiveness(): void {
    if (this.liveTimer !== undefined) {
      clearInterval(this.liveTimer);
      this.liveTimer = undefined;
    }
  }

  private lastScriptedLdr(): { value: number; unit: string } {
    for (let i = this.script.length - 1; i >= 0; i -= 1) {
      const ev = this.script[i]!.event;
      if (ev.type === 'sensor.reading' && ev.payload.slug === LIVENESS_SLUG) {
        return { value: ev.payload.value, unit: ev.payload.unit };
      }
    }
    return { value: 31000, unit: 'raw_u16' }; // matches the fixture's ballpark
  }

  private emit(event: FixtureEvent): void {
    this.seq += 1;
    const stamped = {
      ...event,
      ts: new Date().toISOString(),
      seq: this.seq,
    } as ServerEvent;
    this.opts.onEvent(stamped);
  }
}
