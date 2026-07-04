"""Tiny REST surface — health for ops, board/drivers for deep links, and the
sensor-health/history analytics endpoints.

The WebSocket is the product; REST exists for curl-ability, the frontend's
"view driver source" panel (driver_code rides /api/drivers on purpose — the
registry stores exactly the text that passed on silicon, and showing it is
part of the honesty story), and the devB health panel (/health, /history —
see analytics/health.py).
"""

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

import selfaware
from selfaware.analytics.health import assess_health, assess_trend
from selfaware.api.state import AppState
from selfaware.events.types import ProtocolClass

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
    """Raw (unix_ts, value) points from HistoryStore — the sparkline's data.
    No auth: read-only, same tier as GET /api/drivers."""
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    return {"slug": slug, "unit": record.unit, "points": state.history.series(slug)}


@router.get("/api/drivers/{slug}/health")
async def driver_health(request: Request, slug: str) -> dict[str, Any]:
    """Live health status + short-horizon degradation trend — see
    analytics/health.py for the calculation. Computed from real accumulated
    readings only; "unknown"/"insufficient_data" are honest answers, not
    errors, when a slug is too new to have a real history yet.

    Actuators (OUTPUT class) never publish sensor.reading, so they'd sit at
    "unknown" forever — a status that implies "just wait, it'll resolve"
    when it never will. "not_monitored" says so plainly instead.
    """
    state = _state(request)
    record = state.registry.get(slug)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no driver registered for {slug!r}")
    if record.protocol_class is ProtocolClass.OUTPUT:
        return {
            "slug": slug,
            "status": "not_monitored",
            "reasons": ["this is an actuator — health scoring tracks sensor read drift, not actuator state"],
            "readings_count": 0,
            "baseline_target": 0,
            "trend": {"direction": "insufficient_data", "eta_s": None, "note": None},
        }
    points = state.history.series(slug)
    health = assess_health(points, now=time.time(), expected_interval_s=state.settings.poller_interval_s)
    trend = assess_trend(points)
    return {
        "slug": slug,
        "status": health.status,
        "reasons": health.reasons,
        "readings_count": health.readings_count,
        "baseline_target": health.baseline_target,
        "trend": {"direction": trend.direction, "eta_s": trend.eta_s, "note": trend.note},
    }
