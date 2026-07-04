/**
 * SocketClient — the real WebSocket transport.
 *
 * Reconnect: exponential backoff with FULL jitter (delay = rand() * min(max,
 * base * 2^attempt)), 500ms base -> 8s cap, attempt counter reset on open.
 * stop() suppresses reconnect. send() returns false when the socket is not
 * open — no queueing; the UI disables inputs off the connection slice.
 *
 * Every inbound frame goes through parseServerEvent; nulls (malformed JSON /
 * bad envelope) are counted, logged, and reported via onParseError — never
 * thrown, never fatal to the socket.
 */

import type { AnyEvent, ClientCommand } from '../types/events';
import { parseServerEvent } from './parse';
import type { EventTransport } from './transport';

export type WsStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface SocketOptions {
  url: string;
  onEvent: (ev: AnyEvent) => void;
  onStatus: (s: WsStatus) => void;
  onParseError?: (() => void) | undefined;
  backoff?: { baseMs: number; maxMs: number } | undefined;
}

export class SocketClient implements EventTransport {
  private ws: WebSocket | null = null;
  private stopped = true;
  private attempt = 0;
  private parseErrors = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private readonly baseMs: number;
  private readonly maxMs: number;

  constructor(private readonly opts: SocketOptions) {
    this.baseMs = opts.backoff?.baseMs ?? 500;
    this.maxMs = opts.backoff?.maxMs ?? 8000;
  }

  start(): void {
    if (!this.stopped && this.ws) return; // already running
    this.stopped = false;
    this.connect('connecting');
  }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = undefined;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onclose = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onopen = null;
      try {
        ws.close();
      } catch {
        /* already closed */
      }
    }
    this.opts.onStatus('closed');
  }

  send(cmd: ClientCommand): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(cmd));
      return true;
    }
    return false;
  }

  private connect(phase: 'connecting' | 'reconnecting'): void {
    if (this.stopped) return;
    this.opts.onStatus(phase);
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.opts.onStatus('open');
    };

    ws.onmessage = (e: MessageEvent) => {
      const ev = parseServerEvent(typeof e.data === 'string' ? e.data : String(e.data));
      if (ev === null) {
        this.parseErrors += 1;
        console.warn(`[ws] dropped unparseable frame (#${this.parseErrors})`, e.data);
        this.opts.onParseError?.();
        return;
      }
      this.opts.onEvent(ev);
    };

    ws.onerror = () => {
      // onclose always follows; reconnect is scheduled there.
      try {
        ws.close();
      } catch {
        /* noop */
      }
    };

    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      if (this.stopped) {
        this.opts.onStatus('closed');
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.opts.onStatus('reconnecting');
    const cap = Math.min(this.maxMs, this.baseMs * 2 ** this.attempt);
    const delay = Math.random() * cap; // full jitter
    this.attempt += 1;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect('reconnecting'), delay);
  }
}
