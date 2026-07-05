/**
 * customSpecs — the taught-device shelf. User-authored sensor schemas live in
 * localStorage (this browser IS their registry — the backend accepts them as
 * inline cmd.commission payloads via resolve_spec, no server registry exists).
 * Validation here mirrors the REAL backend rejections (gate.py pin rules,
 * resolve_spec required fields, tool-name charset) so a taught schema can never
 * be insta-rejected by a rule the form already knew about.
 */

import type { CommissionCmdPayload, ProtocolClass } from '../types/events';
import { COMMISSION_PRESETS } from './presets';

const KEY = 'selfaware.customSpecs.v1';

/** A taught device: exactly the inline commission payload + bookkeeping. */
export interface CustomSpec {
  slug: string;
  display_name: string;
  protocol_class: ProtocolClass;
  pins: Record<string, number>;
  i2c_addr?: number | undefined;
  expected_min?: number | undefined;
  expected_max?: number | undefined;
  unit?: string | undefined;
  stimulus_hint?: string | undefined;
  verify_with_slug?: string | undefined;
  extra_context?: string | undefined;
  createdAt: string; // ISO
}

interface Stored {
  version: number;
  specs: CustomSpec[];
}

function read(): CustomSpec[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Stored;
    return Array.isArray(parsed.specs) ? parsed.specs : [];
  } catch {
    return []; // corrupt storage is not a crash — the shelf just looks empty
  }
}

function write(specs: CustomSpec[]): CustomSpec[] {
  try {
    localStorage.setItem(KEY, JSON.stringify({ version: 1, specs } satisfies Stored));
  } catch {
    // storage full/denied: the in-memory list still works for this session
  }
  return specs;
}

export function loadCustomSpecs(): CustomSpec[] {
  return read();
}

/** Upsert by slug (teaching the same slug again refines it). */
export function saveCustomSpec(spec: CustomSpec): CustomSpec[] {
  const rest = read().filter((s) => s.slug !== spec.slug);
  return write([...rest, spec]);
}

export function removeCustomSpec(slug: string): CustomSpec[] {
  return write(read().filter((s) => s.slug !== slug));
}

/** The wire shape: strip bookkeeping, drop empties — resolve_spec fills defaults. */
export function toCommissionPayload(s: CustomSpec): CommissionCmdPayload {
  const p: CommissionCmdPayload = {
    slug: s.slug,
    display_name: s.display_name,
    protocol_class: s.protocol_class,
    pins: s.pins,
  };
  if (s.i2c_addr != null) p.i2c_addr = s.i2c_addr;
  if (s.expected_min != null) p.expected_min = s.expected_min;
  if (s.expected_max != null) p.expected_max = s.expected_max;
  if (s.unit) p.unit = s.unit;
  if (s.stimulus_hint) p.stimulus_hint = s.stimulus_hint;
  if (s.verify_with_slug) p.verify_with_slug = s.verify_with_slug;
  if (s.extra_context) p.extra_context = s.extra_context;
  return p;
}

// --- validation: every rule maps to a real backend rejection ---------------------

/** Slug becomes the `read_<slug>` / `set_<slug>` tool name — lowercase_underscore
 *  matches every built-in slug and the tool-name charset everywhere. */
export const SLUG_RE = /^[a-z][a-z0-9_]{0,23}$/;

/** Mirrors backend settings.adc_capable_pins (config.py) — the gate rejects
 *  ADC(n) on any other pin before the board ever runs. */
export const ADC_CAPABLE_PINS = [26, 27, 28] as const;

export const PROTOCOL_CLASSES: ProtocolClass[] = [
  'analog',
  'digital_bus',
  'pulse_timing',
  'output',
];

/** Required pin roles per class — resolve_spec rejects empty pins; the gate and
 *  the author prompt expect these exact role names. */
export const REQUIRED_PINS: Record<ProtocolClass, string[]> = {
  analog: ['adc'],
  digital_bus: ['sda', 'scl'],
  pulse_timing: ['trig', 'echo'],
  output: [], // one pin of any role (pwm/pin) — checked specially
};

export interface SpecDraft {
  slug: string;
  display_name: string;
  protocol_class: ProtocolClass;
  pins: Record<string, number>;
  i2c_addr?: number | undefined;
  expected_min?: number | undefined;
  expected_max?: number | undefined;
}

/** Human-readable blockers; empty list = safe to teach. */
export function validateSpec(draft: SpecDraft, existingSlugs: string[]): string[] {
  const errors: string[] = [];
  if (!SLUG_RE.test(draft.slug)) {
    errors.push('slug must be lowercase_underscore (it becomes the read_<slug> tool name)');
  } else if (existingSlugs.includes(draft.slug)) {
    errors.push(`"${draft.slug}" is already on the shelf — pick another slug`);
  }
  if (!draft.display_name.trim()) errors.push('give it a display name');

  const pins = draft.pins;
  for (const role of REQUIRED_PINS[draft.protocol_class]) {
    if (!Number.isInteger(pins[role])) errors.push(`${draft.protocol_class} needs a ${role} pin`);
  }
  if (draft.protocol_class === 'output' && Object.keys(pins).length === 0) {
    errors.push('output needs at least one pin');
  }
  if (draft.protocol_class === 'analog') {
    const adc = pins['adc'];
    if (adc != null && !ADC_CAPABLE_PINS.includes(adc as (typeof ADC_CAPABLE_PINS)[number])) {
      errors.push(`ADC pin must be ${ADC_CAPABLE_PINS.join('/')} — the gate rejects anything else`);
    }
  }
  if (draft.protocol_class === 'digital_bus') {
    const addr = draft.i2c_addr;
    if (addr == null) errors.push('digital_bus needs an I2C address (e.g. 0x70)');
    else if (addr < 0x08 || addr > 0x77) errors.push('I2C address must be 0x08–0x77');
  }
  if (
    draft.expected_min != null &&
    draft.expected_max != null &&
    draft.expected_min >= draft.expected_max
  ) {
    errors.push('expected min must be below expected max');
  }
  return errors;
}

/** All slugs a new schema must not collide with. */
export function takenSlugs(customs: CustomSpec[]): string[] {
  return [...COMMISSION_PRESETS.map((p) => p.slug), ...customs.map((c) => c.slug)];
}

/** The same one-glance `class · pins · unit` line the built-in presets carry. */
export function specMeta(s: CustomSpec): string {
  const parts: string[] = [s.protocol_class];
  if (s.i2c_addr != null) parts.push(`i2c 0x${s.i2c_addr.toString(16)}`);
  const pins = Object.values(s.pins);
  if (pins.length) parts.push(`GP${pins.join('/')}`);
  if (s.unit) parts.push(s.unit);
  return parts.join(' · ');
}
