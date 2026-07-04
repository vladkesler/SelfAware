/**
 * FixturePlayer — replays a recorded event script as if a backend were
 * narrating live. Fixtures store events WITHOUT seq/ts; both are stamped at
 * play time (seq monotonic per player, ts = now) so panels see realistic
 * envelopes. Powers `?mock=1` and the landing teaser.
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
}

export class FixturePlayer implements EventTransport {
  private seq = 0;
  private index = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running = false;

  constructor(
    private readonly script: FixtureEntry[],
    private readonly opts: FixturePlayerOpts,
  ) {}

  start(): void {
    if (this.running) return;
    this.running = true;
    this.index = 0;
    this.opts.onStatus?.('open');
    this.scheduleNext();
  }

  stop(): void {
    this.running = false;
    clearTimeout(this.timer);
    this.timer = undefined;
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

  private scheduleNext(): void {
    if (!this.running) return;
    if (this.index >= this.script.length) {
      if (this.opts.loop) {
        this.index = 0; // seq keeps climbing across loops — gaps/monotonicity stay honest
      } else {
        return;
      }
    }
    const entry = this.script[this.index]!;
    const speed = this.opts.speed && this.opts.speed > 0 ? this.opts.speed : 1;
    this.timer = setTimeout(() => {
      if (!this.running) return;
      this.index += 1;
      this.emit(entry.event);
      this.scheduleNext();
    }, entry.afterMs / speed);
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
