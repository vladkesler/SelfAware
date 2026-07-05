/**
 * rings — a DiceBear "rings" avatar per real agent, generated locally (offline,
 * no HTTP API, so the ?mock=1 demo keeps working). The FORM carries identity —
 * each agent's seed yields a distinct arrangement of concentric arcs — while the
 * relay's STATE (idle/active/passed/failed) carries the accent, applied as a thin
 * frame/glow in CSS. So the ring itself stays a restrained, desaturated member of
 * the ion family; the signal-orange strike is reserved for a genuine pass.
 *
 * The style renders on a transparent background already (the only <rect> is the
 * viewbox mask that makes the arcs visible — do NOT remove it, or everything
 * gets masked out), so the arcs sit straight on the near-black bench.
 */

import { createAvatar } from '@dicebear/core';
import { rings } from '@dicebear/collection';
import type { AgentKey } from './agents';

/**
 * Per-agent hue — vivid enough to pop off the cool graphite, one identity each
 * (not a rainbow). Two shades per agent: DiceBear picks per-arc (seeded), so
 * the ring gets depth instead of a flat single-color stroke.
 */
const RING_COLOR: Partial<Record<AgentKey, string[]>> = {
  author: ['4da8ff', '8fd0ff'], // electric blue — writes
  medic: ['2fd4bd', '7ceadb'], // bright teal — repairs
  pilot: ['a58fff', 'cdbfff'], // violet — operates
};

const cache = new Map<string, string>();

/** A themed rings avatar as a data-URI (memoized). Returns '' for non-agents. */
export function ringFor(key: AgentKey): string {
  const color = RING_COLOR[key];
  if (!color) return '';
  const hit = cache.get(key);
  if (hit) return hit;

  const svg = createAvatar(rings, {
    seed: key,
    size: 64,
    ringColor: color,
  }).toString();

  const uri = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  cache.set(key, uri);
  return uri;
}
