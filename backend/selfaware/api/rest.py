"""Tiny REST surface — health for ops, board/drivers for deep links, the
sensor-health/history analytics endpoints, and the two hardware-touching
endpoints the standalone MCP process calls.

The WebSocket is the product; REST exists for curl-ability, the frontend's
"view driver source" panel (driver_code rides /api/drivers on purpose — the
registry stores exactly the text that passed on silicon, and showing it is
part of the honesty story), a pull-shaped view of the same health verdict
the sensor.health event pushes (both go through analytics/health.py's
build_health_payload, so pull and push can never disagree), and now —
read/set — the network seam for mcp_server.py (see that module's docstring
for why MCP runs out-of-process instead of mounting into this app: a
documented SDK limitation, not a style choice). Both go through
registry.perform_read/perform_set, so they inherit the single-lock invariant
and the admission gate for free; nothing here touches BoardSession directly.

Known gap, stated plainly rather than left implicit: the bearer token below
gates only the two POST endpoints. The pre-existing WebSocket cmd.read/cmd.set
commands (api/handlers.py) reach the exact same perform_read/perform_set with
no authentication at all — this closes the newest door, not the older one to
the same room. Fixing that is a separate, larger change (the WS protocol has
no auth concept today) and is out of scope here; don't read "MCP requires a
token" as "actuation requires a token" system-wide.
"""

import hmac
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import selfaware
from selfaware.agents.author import ModelUnavailable, ensure_model_available
from selfaware.analytics.health import build_health_payload
from selfaware.api.state import AppState
from selfaware.bringup.models import ProtocolClass
from selfaware.bringup.service import SpecResolutionError, resolve_spec
from selfaware.events.payloads import CommissionCommand
from selfaware.events.types import EventType
from selfaware.hardware.discovery import KNOWN_I2C_DEVICES, I2CScanError, device_found_payload, scan_i2c_addresses
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


@router.get("/api/drivers/{slug}/history")
async def driver_history(request: Request, slug: str) -> dict[str, Any]:
    """Raw (unix_ts, value) points from HistoryStore — the sparkline's backfill.
    No auth: read-only, same tier as GET /api/drivers."""
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    return {"slug": slug, "unit": record.unit, "points": state.history.series(slug)}


@router.get("/api/drivers/{slug}/health")
async def driver_health(request: Request, slug: str) -> dict[str, Any]:
    """The same verdict the sensor.health event carries, on demand. Computed
    from real accumulated readings only; "unknown"/"insufficient_data" are
    honest answers, not errors, when a slug is too new to have a real history
    yet, and actuators answer "not_monitored" rather than a forever-"unknown"."""
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    payload = build_health_payload(
        record,
        state.history.series(slug),
        now=time.time(),
        interval=state.settings.poller_interval_s,
    )
    return payload.model_dump(mode="json")


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


@router.get("/api/presets")
async def presets(request: Request) -> dict[str, Any]:
    """The commissionable-device catalog: every preset spec, annotated with
    whether it's already commissioned. No auth: read-only config + registry
    state, same tier as GET /api/drivers. extra_context/verify_with_slug are
    excluded — they are author-prompt plumbing, noise to a calling agent."""
    state = _state(request)
    out = []
    for spec in state.settings.default_specs():
        record = state.registry.get(spec.slug)
        tool = f"set_{spec.slug}" if spec.protocol_class is ProtocolClass.OUTPUT else f"read_{spec.slug}"
        out.append(
            {
                **spec.model_dump(mode="json", exclude={"extra_context", "verify_with_slug"}),
                "tool": tool,
                "commissioned": record is not None,
                "driver_status": record.status.value if record is not None else None,
            }
        )
    return {"presets": out}


@router.post("/api/board/scan", dependencies=[Depends(require_mcp_token)])
async def board_scan(request: Request) -> dict[str, Any]:
    """One live I2C scan — the MCP probe_bus tool's body. Publishes the same
    discovery.device_found events the WS cmd.board_scan path emits, so an
    MCP-triggered probe lights up the console's presence cards too."""
    state = _state(request)
    if not state.transport.connected:
        raise HTTPException(status_code=503, detail="board is not connected — nothing to scan")
    try:
        addrs = await scan_i2c_addresses(state.session, state.settings)
    except I2CScanError as exc:
        detail = f"scan_failed: {exc.message}" + (f" — {exc.detail}" if exc.detail else "")
        raise HTTPException(status_code=502, detail=detail) from exc
    matches = []
    for addr in addrs:
        payload = device_found_payload(addr)
        state.bus.publish(EventType.DISCOVERY_DEVICE_FOUND, payload)
        known = KNOWN_I2C_DEVICES.get(addr)
        matches.append(
            {
                "addr": addr,
                "addr_hex": hex(addr),
                "identity": payload.identity,
                "confidence": payload.confidence,
                "preset_slug": (known or {}).get("suggested_spec", {}).get("preset_slug"),
            }
        )
    return {"addresses": addrs, "matches": matches, "note": "live scan taken at call time"}


@router.post("/api/commission", dependencies=[Depends(require_mcp_token)], status_code=202)
async def start_commission(request: Request, body: CommissionCommand) -> dict[str, Any]:
    """Start the AUTHOR->MEDIC self-repair loop for a preset (or full spec) —
    the MCP commission_device tool's body.

    Returns 202 immediately: a commission holds the board exclusively for
    30-120s of LLM codegen + on-silicon testing, far past any sane HTTP or
    MCP-client timeout. Callers poll GET /api/commission/{commission_id};
    the outcome (passed/failed/crashed, with the honest per-attempt record)
    is kept by CommissionService regardless of who is still listening.
    """
    state = _state(request)
    try:
        spec = resolve_spec(body, state.settings)
    except SpecResolutionError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc.message}") from exc
    if not state.transport.connected:
        raise HTTPException(status_code=503, detail="board is not connected")
    if not state.settings.mock_author:
        try:
            ensure_model_available(state.settings)
        except ModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=f"model_unavailable: {exc}") from exc
    commission_id = state.commissioner.enqueue(spec)
    if commission_id is None:
        raise HTTPException(status_code=409, detail="commission_busy: a commission is already running — one at a time")
    return {
        "commission_id": commission_id,
        "slug": spec.slug,
        "status": "running",
        "max_attempts": state.settings.max_attempts,
        "poll": f"/api/commission/{commission_id}",
    }


@router.get("/api/commission/{commission_id}")
async def commission_status(request: Request, commission_id: str) -> dict[str, Any]:
    """Poll one commission: running, or its terminal outcome (passed/failed/
    crashed with attempts_used and the verbatim failure evidence). No auth:
    read-only, same tier as GET /api/drivers."""
    status = _state(request).commissioner.status(commission_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"no commission with id {commission_id!r}")
    return status


class OledSayBody(BaseModel):
    text: str = Field(min_length=1, max_length=120)


@router.post("/api/oled/say", dependencies=[Depends(require_mcp_token)])
async def oled_say(request: Request, body: OledSayBody) -> dict[str, Any]:
    """Show a short message on the physical OLED — the MCP display_message
    tool's body. Honest refusal (409) when the narrator is disabled or the
    display has proven absent; an active commission keeps the screen until
    it finishes, then the message shows for its remaining hold window."""
    state = _state(request)
    narrator = state.extras.get("oled")
    if narrator is None:
        raise HTTPException(status_code=409, detail="OLED narrator is not running")
    if not narrator.say(body.text):
        raise HTTPException(status_code=409, detail="no OLED present (disabled, absent, or not started)")
    return {"ok": True, "text": body.text, "note": "queued for the physical display (~8s hold)"}
