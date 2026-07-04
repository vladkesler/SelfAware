/** Board slice — mirrors the latest board.status / board.connected picture. */

export interface BoardSlice {
  connected: boolean;
  portId: string | null;
  /** MockBoard on the backend (SELFAWARE_MOCK_BOARD) — always badged. */
  mock: boolean;
  /** A commission holds the exclusive lock. */
  busy: boolean;
}

export function initialBoard(): BoardSlice {
  return {
    connected: false,
    portId: null,
    mock: false,
    busy: false,
  };
}
