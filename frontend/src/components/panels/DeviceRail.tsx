/**
 * DeviceRail — the physical world. Presets to teach ("teach it once"),
 * dashed presence cards for what discovery found (identified vs "something
 * is there"), and admitted driver cards whose focal element is the live
 * reading (22px tabular) over a sparkline. Everything commission-adjacent
 * disables while the bench is busy — one wire, one loop.
 */

import type { DriverCard, PresenceCard } from '../../types/domain';
import { COMMISSION_PRESETS, type CommissionPreset } from '../../lib/presets';
import { Sparkline } from '../primitives/Sparkline';

export interface DeviceRailProps {
  drivers: DriverCard[];
  presences: PresenceCard[];
  /** A commission is on the bench — guard every launch affordance. */
  busy: boolean;
  /** Mock board (fixture or MockBoard) — enables the nudge affordance. */
  mock: boolean;
  onRead: (slug: string) => void;
  onSet: (slug: string, level: number) => void;
  onCommission: (presence: PresenceCard) => void;
  /** Launch a preset commission (device that doesn't self-announce, e.g. servo). */
  onCommissionPreset: (slug: string) => void;
  onRescan: () => void;
  /** Mock-only liveness nudge (cmd.stimulate). */
  onStimulate: (slug: string) => void;
  presets?: CommissionPreset[];
}

const CLASS_GLYPH: Record<DriverCard['protocolClass'], string> = {
  analog: '∿',
  digital_bus: '⎍',
  pulse_timing: '⟟',
  output: '⏻',
};

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1);
}

export function DeviceRail({
  drivers,
  presences,
  busy,
  mock,
  onRead,
  onSet,
  onCommission,
  onCommissionPreset,
  onRescan,
  onStimulate,
  presets = COMMISSION_PRESETS,
}: DeviceRailProps) {
  const active = new Set(drivers.map((d) => d.slug));

  return (
    <div className="rail">
      <div className="rail__presets">
        <div className="rail__presets-label machine">
          teach it once
          <button
            type="button"
            className="btn rail__rescan"
            onClick={onRescan}
            disabled={busy}
            title="re-scan the i2c bus"
          >
            rescan bus
          </button>
        </div>
        <div className="rail__presets-btns">
          {presets.map((p) => (
            <button
              key={p.slug}
              type="button"
              className="btn"
              disabled={busy}
              title={
                busy
                  ? 'one wire, one loop — the bench is busy'
                  : active.has(p.slug)
                    ? `${p.slug} already verified — re-runs the loop`
                    : `commission ${p.slug}`
              }
              onClick={() => onCommissionPreset(p.slug)}
            >
              {active.has(p.slug) ? '↻ ' : '+ '}
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {drivers.length === 0 && presences.length === 0 ? (
        <div className="rail__empty machine">
          nothing on the bus yet — plug something in, or pick a preset above
        </div>
      ) : null}

      {presences.map((p) => (
        <div
          key={p.key}
          className={`card card--presence${p.confidence === 'unknown' ? ' card--unknown' : ''}`}
        >
          <div className="card__title">{p.identity ?? 'something is there'}</div>
          <div className="card__meta machine">
            {p.bus === 'i2c' ? `i2c 0x${(p.addr ?? 0).toString(16)}` : `adc GP${p.pin ?? '?'}`}
            {' · '}
            {p.confidence === 'exact' ? 'identified' : 'teach it'}
          </div>
          <div className="card__actions">
            <button type="button" className="btn" disabled={busy} onClick={() => onCommission(p)}>
              commission?
            </button>
          </div>
        </div>
      ))}

      {drivers.map((d) => (
        <div key={d.slug} className={`card card--driver card--${d.status}`}>
          <div className="card__title">
            <span className="card__glyph">{CLASS_GLYPH[d.protocolClass]}</span> {d.displayName}
          </div>
          <div className="card__reading">
            <span className="card__value">
              {d.lastReading !== undefined ? formatValue(d.lastReading) : '—'}
            </span>
            {d.unit ? <span className="card__unit">{d.unit}</span> : null}
            {d.protocolClass !== 'output' ? <Sparkline slug={d.slug} /> : null}
          </div>
          <div className="card__meta machine">
            {d.slug} · {d.protocolClass}
            {d.codeHash ? ` · ${d.codeHash.slice(0, 8)}` : ''}
            {d.status === 'repairing' ? ' · repairing…' : ''}
          </div>
          <div className="card__actions">
            <button type="button" className="btn" disabled={busy} onClick={() => onRead(d.slug)}>
              read
            </button>
            {d.protocolClass === 'output' ? (
              <>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => onSet(d.slug, 1)}
                >
                  set 1
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => onSet(d.slug, 0)}
                >
                  set 0
                </button>
              </>
            ) : mock ? (
              <button
                type="button"
                className="btn"
                disabled={busy}
                title="mock-only: nudge the simulated signal (the stand-in for covering the sensor)"
                onClick={() => onStimulate(d.slug)}
              >
                nudge
              </button>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
