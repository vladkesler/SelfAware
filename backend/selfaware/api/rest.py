"""Tiny REST surface — health for ops, board/drivers for deep links, and the
two hardware-touching endpoints the standalone MCP process calls.

The WebSocket is the product; REST exists for curl-ability, the frontend's
"view driver source" panel (driver_code rides /api/drivers on purpose — the
registry stores exactly the text that passed on silicon, and showing it is
part of the honesty story), and now — read/set — the network seam for
mcp_server.py (see that module's docstring for why MCP runs out-of-process
instead of mounting into this app: a documented SDK limitation, not a style
choice). Both go through registry.perform_read/perform_set, so they inherit
the single-lock invariant and the admission gate for free; nothing here
touches BoardSession directly.

Known gap, stated plainly rather than left implicit: the bearer token below
gates only THESE two endpoints. The pre-existing WebSocket cmd.read/cmd.set
commands (api/handlers.py) reach the exact same perform_read/perform_set with
no authentication at all — this closes the newest door, not the older one to
the same room. Fixing that is a separate, larger change (the WS protocol has
no auth concept today) and is out of scope here; don't read "MCP requires a
token" as "actuation requires a token" system-wide.
"""

import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

import selfaware
from selfaware.api.state import AppState
from selfaware.registry.store import DriverToolError

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


def _state(request: Request) -> AppState:
    return request.app.state.selfaware


def require_mcp_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Guard for the two hardware-touching endpoints below.

    Fails closed: an unset SELFAWARE_MCP_TOKEN means these endpoints refuse
    every request (403 "not configured"), never "open to anyone" — the same
    honest-degrade philosophy as the rest of the app, just for a boundary
    where the failure mode is real actuation, not a missing dashboard widget.
    Comparison is constant-time (hmac.compare_digest) since this guards real
    actuation, not just a login page.
    """
    expected = _state(request).settings.mcp_token
    if not expected:
        raise HTTPException(status_code=403, detail="MCP token not configured (SELFAWARE_MCP_TOKEN unset)")
    if creds is None or not hmac.compare_digest(creds.credentials, expected):
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


class SetLevelBody(BaseModel):
    level: float


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": selfaware.__version__}


@router.get("/api/board")
async def board(request: Request) -> dict[str, Any]:
    return _state(request).session.board_status().model_dump(mode="json")


@router.get("/api/drivers")
async def drivers(request: Request) -> list[dict[str, Any]]:
    """Every registered driver, INCLUDING driver_code (see module docstring)."""
    return [record.model_dump(mode="json") for record in _state(request).registry.list()]


@router.get("/api/drivers/{slug}")
async def driver(request: Request, slug: str) -> dict[str, Any]:
    record = _state(request).registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    return record.model_dump(mode="json")


@router.post("/api/drivers/{slug}/read", dependencies=[Depends(require_mcp_token)])
async def read_driver(request: Request, slug: str) -> dict[str, Any]:
    """Take a live reading through <slug>'s verified driver — the MCP read tool's body.

    Same perform_read the copilot's read_<slug> tool calls: admission-gated
    (raises if slug isn't ACTIVE), single-lock serialized, hot-swap safe. The
    upfront transport.connected check mirrors api/handlers.py's cmd.read, so
    a disconnected board answers the same clean board_offline every other
    caller gets, not a raw DriverToolError from deep inside perform_read.
    """
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    if not state.transport.connected:
        raise HTTPException(status_code=503, detail="board is not connected")
    try:
        value = await state.registry.perform_read(state.session, slug)
    except DriverToolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, "value": value, "unit": record.unit, "read_at": record.last_read_at}


@router.post("/api/drivers/{slug}/set", dependencies=[Depends(require_mcp_token)])
async def set_driver(request: Request, slug: str, body: SetLevelBody) -> dict[str, Any]:
    """Drive <slug>'s actuator to body.level — the MCP set tool's body."""
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    if not state.transport.connected:
        raise HTTPException(status_code=503, detail="board is not connected")
    try:
        await state.registry.perform_set(state.session, slug, body.level)
    except DriverToolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, "level": body.level, "ok": True}
