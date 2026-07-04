/**
 * BoardStatus — the thin top strip: transport status, board state, port,
 * MOCK badge (fixture transport OR backend MockBoard — mock is always
 * badged, never silent), and the protocol-version mismatch warning.
 */

import type { WsStatus } from '../../lib/ws';
import type { BoardSlice } from '../../state/slices/board';
import { PROTOCOL_VERSION } from '../../types/events';
import { StatusDot } from '../primitives/StatusDot';

export interface BoardStatusProps {
  ws: WsStatus;
  board: BoardSlice;
  /** Fixture transport live (?mock=1 / VITE_MOCK). */
  mock: boolean;
  protocolMismatch: boolean;
}

export function BoardStatus({ ws, board, mock, protocolMismatch }: BoardStatusProps) {
  const wsDot = ws === 'open' ? 'live' : ws === 'closed' ? 'alert' : 'idle';
  const boardDot = board.connected ? (board.busy ? 'idle' : 'live') : 'alert';

  return (
    <div className="statusbar machine">
      <span className="statusbar__item">
        <StatusDot state={wsDot} /> ws {ws}
      </span>
      <span className="statusbar__item">
        <StatusDot state={boardDot} /> board{' '}
        {board.connected ? `${board.portId ?? '?'}${board.busy ? ' · busy' : ' · idle'}` : 'offline'}
      </span>
      {mock || board.mock ? <span className="badge badge--mock">MOCK</span> : null}
      {protocolMismatch ? (
        <span className="statusbar__warn">
          ⚠ protocol mismatch — client v{PROTOCOL_VERSION}, server differs; expect raw rows
        </span>
      ) : null}
      <span className="statusbar__spacer" />
      <span className="statusbar__brand">selfaware</span>
    </div>
  );
}
