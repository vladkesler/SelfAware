/**
 * BoardStatus — the fascia. Deliberately quiet: brand, the COMMISSION preset
 * picker (teach-it-once, the way new parts get on the bench), link + board
 * state, the MOCK badge, the model the agents run on, and a live "senses"
 * count. The old instrument chrome (seq ticker, wall clock, code hashes) is
 * gone — nothing here may outshine the stage.
 */

import { useEffect, useRef, useState } from 'react';
import type { WsStatus } from '../../lib/ws';
import type { BoardSlice } from '../../state/slices/board';
import type { CommissionPreset } from '../../lib/presets';
import type { CustomSpec } from '../../lib/customSpecs';
import { PROTOCOL_VERSION } from '../../types/events';
import { StatusDot } from '../primitives/StatusDot';
import { ConnectAgent } from './ConnectAgent';
import { TeachDevice } from './TeachDevice';

export interface BoardStatusProps {
  ws: WsStatus;
  board: BoardSlice;
  mock: boolean;
  protocolMismatch: boolean;
  model?: string | undefined;
  /** Number of admitted, live drivers — the machine's accreted senses. */
  senses: number;
  busySlug?: string | undefined;
  lastError?: { code: string; message: string; at: string } | undefined;
  presets: CommissionPreset[];
  /** The taught-device shelf (localStorage) — rendered by TeachDevice. */
  customSpecs: CustomSpec[];
  /** Disable the commission picker while the bench is busy. */
  busy: boolean;
  onCommission: (slug: string) => void;
  onTeach: (spec: CustomSpec) => void;
  onTeachAndCommission: (spec: CustomSpec) => void;
  onRemoveCustom: (slug: string) => void;
}

const ERROR_DISMISS_MS = 6000;

function shortModel(model: string | undefined): string | null {
  if (!model) return null;
  return model.includes(':') ? model.split(':').slice(1).join(':') : model;
}

export function BoardStatus({
  ws,
  board,
  mock,
  protocolMismatch,
  model,
  senses,
  busySlug,
  lastError,
  presets,
  customSpecs,
  busy,
  onCommission,
  onTeach,
  onTeachAndCommission,
  onRemoveCustom,
}: BoardStatusProps) {
  const menuRef = useRef<HTMLDetailsElement>(null);

  const [errorVisible, setErrorVisible] = useState(false);
  useEffect(() => {
    if (!lastError) return;
    setErrorVisible(true);
    const id = setTimeout(() => setErrorVisible(false), ERROR_DISMISS_MS);
    return () => clearTimeout(id);
  }, [lastError]);

  const wsDot = ws === 'open' ? 'live' : ws === 'closed' ? 'alert' : 'idle';
  const boardDot = board.connected ? (board.busy ? 'busy' : 'live') : 'alert';
  const modelLabel = shortModel(model);

  const pick = (slug: string) => {
    if (menuRef.current) menuRef.current.open = false;
    onCommission(slug);
  };

  return (
    <div className="fascia machine">
      <span className="fascia__brand">selfaware</span>

      <details className="fascia__cmd" ref={menuRef}>
        <summary className="fascia__cmd-btn">commission ▸</summary>
        <div className="fascia__cmd-menu">
          <div className="fascia__cmd-label">on the board</div>
          {presets
            .filter((p) => !p.custom)
            .map((p) => (
              <button
                key={p.slug}
                type="button"
                className="fascia__cmd-item cmd-item"
                disabled={busy}
                onClick={() => pick(p.slug)}
              >
                <span className="cmd-item__name">{p.label}</span>
                <span className="cmd-item__meta">{p.meta}</span>
              </button>
            ))}
          {presets.some((p) => p.custom) ? (
            <>
              <div className="fascia__cmd-label cmd-taught-label">
                <span className="cmd-taught-dot" aria-hidden /> taught by you
              </div>
              {presets
                .filter((p) => p.custom)
                .map((p) => (
                  <div key={p.slug} className="cmd-item-row">
                    <button
                      type="button"
                      className="fascia__cmd-item cmd-item"
                      disabled={busy}
                      onClick={() => pick(p.slug)}
                    >
                      <span className="cmd-item__name">{p.label}</span>
                      <span className="cmd-item__meta">{p.meta}</span>
                    </button>
                    <button
                      type="button"
                      className="cmd-item-x"
                      aria-label={`forget ${p.slug}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveCustom(p.slug);
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
            </>
          ) : null}
        </div>
      </details>

      <TeachDevice
        customSpecs={customSpecs}
        busy={busy}
        onTeach={onTeach}
        onTeachAndCommission={onTeachAndCommission}
        onRemoveCustom={onRemoveCustom}
      />

      <ConnectAgent />

      {protocolMismatch ? (
        <span className="fascia__warn">⚠ protocol mismatch — client v{PROTOCOL_VERSION}</span>
      ) : null}
      {errorVisible && lastError ? (
        <span className="fascia__error" role="alert">
          {lastError.code} — {lastError.message}
        </span>
      ) : null}

      <span className="fascia__spacer" />

      <span className="fascia__item">
        <StatusDot state={wsDot} /> link <strong>{ws}</strong>
      </span>
      <span className="fascia__item">
        <StatusDot state={boardDot} />{' '}
        {board.connected ? (
          board.busy ? (
            <>commissioning{busySlug ? <strong> · {busySlug}</strong> : null}</>
          ) : (
            <strong>{board.portId ?? 'board'}</strong>
          )
        ) : (
          'board offline'
        )}
      </span>
      {mock || board.mock ? <span className="badge badge--mock">MOCK</span> : null}
      <span className="fascia__item">
        senses <strong>{senses}</strong>
      </span>
      {modelLabel ? <span className="fascia__model">{modelLabel}</span> : null}
    </div>
  );
}
