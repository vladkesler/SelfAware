/**
 * TeachDevice — the fascia's "teach ▸" popover: declare a new device once and
 * it joins the commission shelf. No theater: the form emits the SAME inline
 * cmd.commission payload the backend's resolve_spec already accepts — pins,
 * plausibility window, and the extra-context note the author agent reads
 * before writing the driver. Validation mirrors the real gate rules (ADC pin
 * allowlist, required roles, slug charset) so a taught schema is never dead on
 * arrival. Schemas persist in localStorage — this browser is the shelf.
 */

import { useMemo, useRef, useState } from 'react';
import type { ProtocolClass } from '../../types/events';
import {
  ADC_CAPABLE_PINS,
  PROTOCOL_CLASSES,
  takenSlugs,
  specMeta,
  validateSpec,
  type CustomSpec,
} from '../../lib/customSpecs';

export interface TeachDeviceProps {
  customSpecs: CustomSpec[];
  /** Board busy — disables the commission button, never the save. */
  busy: boolean;
  onTeach: (spec: CustomSpec) => void;
  onTeachAndCommission: (spec: CustomSpec) => void;
  onRemoveCustom: (slug: string) => void;
}

/** Per-class defaults for the plausibility window + unit. */
const CLASS_DEFAULTS: Record<ProtocolClass, { min: string; max: string; unit: string }> = {
  analog: { min: '0', max: '100', unit: '%' },
  digital_bus: { min: '', max: '', unit: '' },
  pulse_timing: { min: '2', max: '400', unit: 'cm' },
  output: { min: '', max: '', unit: '' },
};

const num = (v: string): number | undefined => {
  if (!v.trim()) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
};

/** I2C addresses read naturally in hex — accept "0x70" or "112". */
const addrNum = (v: string): number | undefined => {
  const t = v.trim().toLowerCase();
  if (!t) return undefined;
  const n = t.startsWith('0x') ? parseInt(t, 16) : parseInt(t, 10);
  return Number.isFinite(n) ? n : undefined;
};

interface Draft {
  slug: string;
  displayName: string;
  cls: ProtocolClass;
  adcPin: number;
  sda: string;
  scl: string;
  i2cAddr: string;
  trig: string;
  echo: string;
  outRole: 'pwm' | 'pin';
  outPin: string;
  verifyWith: string;
  min: string;
  max: string;
  unit: string;
  stimulusHint: string;
  extraContext: string;
}

const EMPTY: Draft = {
  slug: '',
  displayName: '',
  cls: 'analog',
  adcPin: 28,
  sda: '4',
  scl: '5',
  i2cAddr: '',
  trig: '14',
  echo: '15',
  outRole: 'pwm',
  outPin: '',
  verifyWith: '',
  min: '0',
  max: '100',
  unit: '%',
  stimulusHint: '',
  extraContext: '',
};

/** Pins assembled from the ACTIVE class's fields only — a class switch can
 *  never leak stale roles into the payload. */
function draftPins(d: Draft): Record<string, number> {
  switch (d.cls) {
    case 'analog':
      return { adc: d.adcPin };
    case 'digital_bus': {
      const pins: Record<string, number> = {};
      const sda = num(d.sda);
      const scl = num(d.scl);
      if (sda != null) pins['sda'] = sda;
      if (scl != null) pins['scl'] = scl;
      return pins;
    }
    case 'pulse_timing': {
      const pins: Record<string, number> = {};
      const trig = num(d.trig);
      const echo = num(d.echo);
      if (trig != null) pins['trig'] = trig;
      if (echo != null) pins['echo'] = echo;
      return pins;
    }
    case 'output': {
      const pin = num(d.outPin);
      return pin != null ? { [d.outRole]: pin } : {};
    }
  }
}

function draftToSpec(d: Draft): CustomSpec {
  return {
    slug: d.slug.trim(),
    display_name: d.displayName.trim(),
    protocol_class: d.cls,
    pins: draftPins(d),
    i2c_addr: d.cls === 'digital_bus' ? addrNum(d.i2cAddr) : undefined,
    expected_min: num(d.min),
    expected_max: num(d.max),
    unit: d.unit.trim() || undefined,
    stimulus_hint: d.stimulusHint.trim() || undefined,
    verify_with_slug: d.cls === 'output' ? d.verifyWith.trim() || undefined : undefined,
    extra_context: d.extraContext.trim() || undefined,
    createdAt: new Date().toISOString(),
  };
}

export function TeachDevice({
  customSpecs,
  busy,
  onTeach,
  onTeachAndCommission,
  onRemoveCustom,
}: TeachDeviceProps) {
  const menuRef = useRef<HTMLDetailsElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [pasted, setPasted] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [imported, setImported] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [viewing, setViewing] = useState<string | null>(null);

  const existing = useMemo(() => takenSlugs(customSpecs), [customSpecs]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const setClass = (cls: ProtocolClass) =>
    setDraft((d) => ({ ...d, cls, ...CLASS_DEFAULTS[cls] }));

  const importJson = (text: string, silent = false) => {
    if (!text.trim()) {
      setImportError('paste a schema above or upload a .json file first');
      setImported(false);
      return;
    }
    try {
      const j = JSON.parse(text) as Record<string, unknown>;
      const cls = PROTOCOL_CLASSES.includes(j['protocol_class'] as ProtocolClass)
        ? (j['protocol_class'] as ProtocolClass)
        : 'analog';
      const pins = (j['pins'] ?? {}) as Record<string, unknown>;
      const str = (k: string) => (typeof j[k] === 'string' ? (j[k] as string) : '');
      const numStr = (v: unknown) => (typeof v === 'number' ? String(v) : '');
      const rawAddr = j['i2c_addr'];
      const outEntry = Object.entries(pins).find(([r]) => r !== 'adc');
      setDraft({
        slug: str('slug'),
        displayName: str('display_name'),
        cls,
        adcPin: typeof pins['adc'] === 'number' ? (pins['adc'] as number) : 28,
        sda: numStr(pins['sda']) || '4',
        scl: numStr(pins['scl']) || '5',
        i2cAddr:
          typeof rawAddr === 'number'
            ? `0x${rawAddr.toString(16)}`
            : typeof rawAddr === 'string'
              ? rawAddr
              : '',
        trig: numStr(pins['trig']) || '14',
        echo: numStr(pins['echo']) || '15',
        outRole: cls === 'output' && outEntry && outEntry[0] === 'pin' ? 'pin' : 'pwm',
        outPin: cls === 'output' && outEntry ? numStr(outEntry[1]) : '',
        verifyWith: str('verify_with_slug'),
        min: numStr(j['expected_min']),
        max: numStr(j['expected_max']),
        unit: str('unit'),
        stimulusHint: str('stimulus_hint'),
        extraContext: str('extra_context'),
      });
      setImportError(null);
      setImported(true);
      setErrors([]);
    } catch {
      if (!silent) setImportError('not valid JSON — check the paste');
      setImported(false);
    }
  };

  const submit = (commission: boolean) => {
    const spec = draftToSpec(draft);
    const problems = validateSpec(
      {
        slug: spec.slug,
        display_name: spec.display_name,
        protocol_class: spec.protocol_class,
        pins: spec.pins,
        i2c_addr: spec.i2c_addr,
        expected_min: spec.expected_min,
        expected_max: spec.expected_max,
      },
      existing,
    );
    setErrors(problems);
    if (problems.length) return;
    if (commission) onTeachAndCommission(spec);
    else onTeach(spec);
    setDraft(EMPTY);
    setPasted('');
    setImported(false);
    if (menuRef.current) menuRef.current.open = false;
  };

  return (
    <details className="fascia__cmd teach" ref={menuRef}>
      <summary className="fascia__cmd-btn">teach ▸</summary>
      <div className="fascia__cmd-menu teach__menu">
        <div className="fascia__cmd-label">teach it a new device</div>

        {/* a schema arrives by paste (auto-imports) or file upload; the fields
            below stay the source of truth so validation always runs */}
        <div className="teach__import">
          <textarea
            className="input teach__paste"
            rows={2}
            placeholder="paste a device schema (JSON)…"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text');
              if (text.trim()) importJson(text, true); // fill on the paste itself
            }}
          />
          <div className="teach__import-btns">
            <button type="button" className="btn" onClick={() => importJson(pasted)}>
              import
            </button>
            <button type="button" className="btn" onClick={() => fileRef.current?.click()}>
              upload .json
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                void f.text().then((text) => {
                  setPasted(text);
                  importJson(text);
                });
                e.target.value = ''; // same file can be re-picked
              }}
            />
          </div>
        </div>
        {importError ? <div className="teach__errors">{importError}</div> : null}
        {imported && !importError ? (
          <div className="teach__imported">schema imported ✓ — review below, then teach</div>
        ) : null}

        <div className="teach__grid">
          <label className="teach__field">
            <span className="teach__key">slug</span>
            <input
              className="input"
              value={draft.slug}
              placeholder="soil"
              onChange={(e) => set('slug', e.target.value)}
            />
          </label>
          <label className="teach__field">
            <span className="teach__key">display name</span>
            <input
              className="input"
              value={draft.displayName}
              placeholder="Soil moisture"
              onChange={(e) => set('displayName', e.target.value)}
            />
          </label>
        </div>

        <label className="teach__field">
          <span className="teach__key">protocol class</span>
          <select
            className="input teach__select"
            value={draft.cls}
            onChange={(e) => setClass(e.target.value as ProtocolClass)}
          >
            {PROTOCOL_CLASSES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        {draft.cls === 'analog' ? (
          <div className="teach__field">
            <span className="teach__key">adc pin</span>
            <div className="teach__pins">
              {ADC_CAPABLE_PINS.map((pin) => (
                <button
                  key={pin}
                  type="button"
                  className="teach__pin"
                  data-on={draft.adcPin === pin ? '' : undefined}
                  onClick={() => set('adcPin', pin)}
                >
                  GP{pin}
                  {pin === 26 ? <span className="teach__pin-note">pot</span> : null}
                  {pin === 27 ? <span className="teach__pin-note">ldr</span> : null}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {draft.cls === 'digital_bus' ? (
          <div className="teach__grid teach__grid--three">
            <label className="teach__field">
              <span className="teach__key">sda</span>
              <input className="input" value={draft.sda} onChange={(e) => set('sda', e.target.value)} />
            </label>
            <label className="teach__field">
              <span className="teach__key">scl</span>
              <input className="input" value={draft.scl} onChange={(e) => set('scl', e.target.value)} />
            </label>
            <label className="teach__field">
              <span className="teach__key">i2c addr</span>
              <input
                className="input"
                value={draft.i2cAddr}
                placeholder="0x70"
                onChange={(e) => set('i2cAddr', e.target.value)}
              />
            </label>
          </div>
        ) : null}

        {draft.cls === 'pulse_timing' ? (
          <div className="teach__grid">
            <label className="teach__field">
              <span className="teach__key">trig</span>
              <input className="input" value={draft.trig} onChange={(e) => set('trig', e.target.value)} />
            </label>
            <label className="teach__field">
              <span className="teach__key">echo</span>
              <input className="input" value={draft.echo} onChange={(e) => set('echo', e.target.value)} />
            </label>
          </div>
        ) : null}

        {draft.cls === 'output' ? (
          <div className="teach__grid teach__grid--three">
            <label className="teach__field">
              <span className="teach__key">pin role</span>
              <select
                className="input teach__select"
                value={draft.outRole}
                onChange={(e) => set('outRole', e.target.value as 'pwm' | 'pin')}
              >
                <option value="pwm">pwm</option>
                <option value="pin">pin</option>
              </select>
            </label>
            <label className="teach__field">
              <span className="teach__key">pin</span>
              <input
                className="input"
                value={draft.outPin}
                placeholder="20"
                onChange={(e) => set('outPin', e.target.value)}
              />
            </label>
            <label className="teach__field">
              <span className="teach__key">verify with</span>
              <input
                className="input"
                value={draft.verifyWith}
                placeholder="sensor slug"
                onChange={(e) => set('verifyWith', e.target.value)}
              />
            </label>
          </div>
        ) : null}

        <div className="teach__grid teach__grid--three">
          <label className="teach__field">
            <span className="teach__key">expected min</span>
            <input className="input" value={draft.min} onChange={(e) => set('min', e.target.value)} />
          </label>
          <label className="teach__field">
            <span className="teach__key">expected max</span>
            <input className="input" value={draft.max} onChange={(e) => set('max', e.target.value)} />
          </label>
          <label className="teach__field">
            <span className="teach__key">unit</span>
            <input className="input" value={draft.unit} onChange={(e) => set('unit', e.target.value)} />
          </label>
        </div>

        <label className="teach__field">
          <span className="teach__key">stimulus hint</span>
          <input
            className="input"
            value={draft.stimulusHint}
            placeholder="cover the sensor with your hand"
            onChange={(e) => set('stimulusHint', e.target.value)}
          />
        </label>

        <label className="teach__field">
          <span className="teach__key">extra context</span>
          <textarea
            className="input teach__context"
            rows={4}
            value={draft.extraContext}
            placeholder="wiring, normalization, protocol quirks…"
            onChange={(e) => set('extraContext', e.target.value)}
          />
          <span className="teach__hint">
            the note the author agent reads before writing the driver
          </span>
        </label>

        {errors.length ? (
          <ul className="teach__errors">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}

        <div className="teach__actions">
          <button
            type="button"
            className="btn btn--accent"
            disabled={busy}
            onClick={() => submit(true)}
          >
            teach + commission
          </button>
          <button type="button" className="btn" onClick={() => submit(false)}>
            save to shelf
          </button>
        </div>

        {customSpecs.length ? (
          <div className="teach__shelf">
            <div className="fascia__cmd-label">on the shelf</div>
            {customSpecs.map((c) => (
              <div key={c.slug} className="teach__taught">
                <div className="teach__taught-row">
                  <span className="teach__taught-name">{c.display_name}</span>
                  <span className="teach__taught-meta">{specMeta(c)}</span>
                  <button
                    type="button"
                    className="teach__taught-btn"
                    onClick={() => setViewing(viewing === c.slug ? null : c.slug)}
                  >
                    {viewing === c.slug ? 'hide' : 'view'}
                  </button>
                  <button
                    type="button"
                    className="teach__taught-btn teach__taught-btn--x"
                    aria-label={`forget ${c.slug}`}
                    onClick={() => onRemoveCustom(c.slug)}
                  >
                    ×
                  </button>
                </div>
                {viewing === c.slug ? (
                  <pre className="connect__code connect__code--json teach__taught-json">
                    {JSON.stringify(
                      { ...c, createdAt: undefined },
                      (_k, v: unknown) => (v === undefined ? undefined : v),
                      2,
                    )}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}
