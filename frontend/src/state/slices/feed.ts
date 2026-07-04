/**
 * Feed slice — the play-by-play. EVERY event (known or unknown) lands here.
 * The RingBuffer is mutated in place; dispatch replaces the slice object so
 * zustand subscribers see a new reference per event.
 */

import type { AnyEvent } from '../../types/events';
import { RingBuffer } from '../../lib/ring';

export const FEED_CAP = 500;

export interface FeedSlice {
  events: RingBuffer<AnyEvent>;
}

export function initialFeed(): FeedSlice {
  return { events: new RingBuffer<AnyEvent>(FEED_CAP) };
}
