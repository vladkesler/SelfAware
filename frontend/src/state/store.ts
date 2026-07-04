/**
 * The zustand store — one store, seven slices, writable from OUTSIDE React:
 * the transport sink calls useStore.getState().apply(ev) directly, and the
 * ReadingScope reads samples via transient store.subscribe (no React
 * re-render per sample; see slices/readings.ts).
 *
 * apply() delegates to state/dispatch.ts — the single event→state seam.
 */

import { create } from 'zustand';
import type { AnyEvent } from '../types/events';
import type { WsStatus } from '../lib/ws';
import { applyEvent } from './dispatch';
import { type ConnectionSlice, initialConnection } from './slices/connection';
import { type BoardSlice, initialBoard } from './slices/board';
import { type CommissionSlice, initialCommission } from './slices/commission';
import { type FeedSlice, initialFeed } from './slices/feed';
import { type DriversSlice, initialDrivers } from './slices/drivers';
import { type ReadingsSlice, initialReadings } from './slices/readings';
import { type ChatSlice, initialChat } from './slices/chat';

export interface StoreState {
  connection: ConnectionSlice;
  board: BoardSlice;
  commission: CommissionSlice;
  feed: FeedSlice;
  drivers: DriversSlice;
  readings: ReadingsSlice;
  chat: ChatSlice;

  /** THE event entry point — the transport sink. Delegates to dispatch.ts. */
  apply: (ev: AnyEvent) => void;
  /** Transport status → connection slice (wired in useTransport). */
  setWsStatus: (status: WsStatus) => void;
  /** Fixture-mode badge (?mock=1 / VITE_MOCK). */
  setMockMode: (mock: boolean) => void;
  /** A frame failed parseServerEvent — counted, never fatal. */
  noteParseError: () => void;
}

export type StoreSet = (
  partial: Partial<StoreState> | ((s: StoreState) => Partial<StoreState>),
) => void;
export type StoreGet = () => StoreState;

export const useStore = create<StoreState>()((set, get) => ({
  connection: initialConnection(),
  board: initialBoard(),
  commission: initialCommission(),
  feed: initialFeed(),
  drivers: initialDrivers(),
  readings: initialReadings(),
  chat: initialChat(),

  apply: (ev) => applyEvent(ev, set, get),
  setWsStatus: (status) => set((s) => ({ connection: { ...s.connection, status } })),
  setMockMode: (mock) => set((s) => ({ connection: { ...s.connection, mock } })),
  noteParseError: () =>
    set((s) => ({ connection: { ...s.connection, parseErrors: s.connection.parseErrors + 1 } })),
}));
