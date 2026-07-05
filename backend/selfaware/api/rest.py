"""Tiny REST surface — health for ops, board/drivers for deep links, and the
sensor-health/history analytics endpoints.

The WebSocket is the product; REST exists for curl-ability, the frontend's
"view driver source" panel (driver_code rides /api/drivers on purpose — the
registry stores exactly the text that passed on silicon, and showing it is
part of the honesty story), and a pull-shaped view of the same health verdict
the sensor.health event pushes (both go through analytics/health.py's
build_health_payload, so pull and push can never disagree).
"""

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

import selfaware
from selfaware.analytics.health import build_health_payload
from selfaware.api.state import AppState

router = APIRouter()


def _state(request: Request) -> AppState:
    return request.app.state.selfaware


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
