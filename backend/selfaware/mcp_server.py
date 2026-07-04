"""Standalone MCP transport — a SEPARATE process from the main FastAPI backend.

Run via `python -m selfaware.mcp_server` (own uvicorn-managed HTTP transport).
This does NOT mount into create_app()'s ASGI app — that pattern is a
documented, currently-unresolved limitation of the MCP Python SDK's
Streamable HTTP transport (redirect loops, and "Task group is not
initialized. Make sure to use run()." — see
https://github.com/modelcontextprotocol/python-sdk/issues/1367). The only
confirmed-working deployment mode is `mcp.run()` owning its own process, so
that's what this module does.

This process never touches BoardSession, the registry, or the EventBus
directly — the single-lock invariant (hardware/session.py::BoardSession)
belongs to the main backend process alone. Instead:

  * GET  /api/drivers            — full reconciliation: at startup AND on
                                    every (re)connect below, not just once
  * WS   /ws                     — driver.registered / driver.updated is the
                                    LIVE-UPDATE signal; GET /api/drivers is
                                    still the source of truth reconciled
                                    against, since a dropped connection can
                                    silently lose events in the gap
  * POST /api/drivers/{slug}/read  and  /set   — the actual hardware call,
    bearer-authenticated (api/rest.py::require_mcp_token)

Every driver.* event triggers a fresh GET /api/drivers/{slug} rather than
trusting the event payload directly: DriverUpdatedPayload carries no
protocol_class (see events/payloads.py), so re-fetching is the only way to
know whether a repair also changed read<->set, and it makes REGISTERED and
UPDATED one code path instead of two slightly-different ones. Records are
parsed into the real DriverRecord/ProtocolClass/DriverStatus types (the
GET responses are exactly record.model_dump(mode="json")) instead of raw
dicts, so this file shares the exact tool-description wording and the exact
protocol-class enum the in-process copilot toolset uses
(registry/models.py::DriverRecord.read_description/set_description) — no
second, hand-written copy to drift out of sync.

Honesty floor for callers we don't control: every tool description and every
response payload says the reading is live, taken at call time — since an
external agent's own system prompt is outside our control, the guardrail has
to travel with the data, not depend on the caller's instructions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
import websockets
from fastmcp import FastMCP

from selfaware.registry.models import DriverRecord, DriverStatus, ProtocolClass

logger = logging.getLogger("selfaware.mcp_server")

BACKEND_URL = os.environ.get("SELFAWARE_MCP_BACKEND_URL", "http://localhost:8000")
WS_URL = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
TOKEN = os.environ.get("SELFAWARE_MCP_TOKEN", "")
HOST = os.environ.get("SELFAWARE_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("SELFAWARE_MCP_PORT", "8001"))

mcp: FastMCP = FastMCP("SelfAware", on_duplicate="replace")

# slug -> "read" | "set", tracked locally so a repair that flips protocol
# class (rare, but the registry doesn't forbid it) can be reconciled instead
# of leaving a stale tool pointing at the wrong verb, and so a driver that
# leaves ACTIVE status can have its tool removed instead of left dangling.
_armed: dict[str, str] = {}

_client: httpx.AsyncClient | None = None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def _make_read_tool(slug: str):
    async def read_tool() -> dict[str, Any]:
        assert _client is not None
        resp = await _client.post(f"/api/drivers/{slug}/read", headers=_headers())
        if resp.status_code != 200:
            raise RuntimeError(f"read_{slug}: backend said {resp.status_code} — {resp.text}")
        data = resp.json()
        return {
            "value": data["value"],
            "unit": data.get("unit", ""),
            "read_at": data.get("read_at"),
            "note": "live reading, taken at call time — re-call for the current value, do not cache",
        }

    read_tool.__name__ = f"read_{slug}"
    return read_tool


def _make_set_tool(slug: str):
    async def set_tool(level: float) -> dict[str, Any]:
        assert _client is not None
        resp = await _client.post(f"/api/drivers/{slug}/set", json={"level": level}, headers=_headers())
        if resp.status_code != 200:
            raise RuntimeError(f"set_{slug}: backend said {resp.status_code} — {resp.text}")
        return {"slug": slug, "level": level, "ok": True}

    set_tool.__name__ = f"set_{slug}"
    return set_tool


def _remove_armed(slug: str) -> None:
    """Best-effort tool removal. mcp.local_provider is the current (already
    once-renamed) internal API for this in the installed fastmcp version —
    if it moves again, we log loudly rather than pretend nothing happened."""
    prev = _armed.pop(slug, None)
    if prev is None:
        return
    stale_name = f"{prev}_{slug}"
    try:
        mcp.local_provider.remove_tool(stale_name)
    except Exception:  # noqa: BLE001 — best-effort; fastmcp's internal API has already changed once
        logger.error("mcp: could not remove stale tool %s — check fastmcp's remove-tool API", stale_name)


def _arm(record: DriverRecord) -> None:
    """(Re-)register the correct tool for one driver record, or remove it.

    Handles three cases: a driver that's no longer ACTIVE gets de-armed (a
    demotion — e.g. a failed re-commission — must not leave a dead tool
    behind); a driver whose protocol class flipped gets its stale verb
    removed before the new one is added (read_<slug> vs set_<slug> are
    different tool NAMES, so on_duplicate="replace" alone can't handle this);
    everything else is the common case fastmcp's replace-on-duplicate covers
    for free.
    """
    if record.status is not DriverStatus.ACTIVE:
        _remove_armed(record.slug)
        return

    kind = "set" if record.protocol_class is ProtocolClass.OUTPUT else "read"
    prev = _armed.get(record.slug)
    if prev is not None and prev != kind:
        _remove_armed(record.slug)

    if kind == "set":
        mcp.tool(_make_set_tool(record.slug), name=f"set_{record.slug}", description=record.set_description())
    else:
        mcp.tool(_make_read_tool(record.slug), name=f"read_{record.slug}", description=record.read_description())
    _armed[record.slug] = kind
    logger.info("mcp: armed %s_%s", kind, record.slug)


async def _reconcile_all() -> None:
    """Full sync against the registry's actual current state: GET /api/drivers,
    arm/de-arm every slug found (including ones not yet seen), and de-arm
    anything we think is armed that the backend no longer lists at all (a
    restarted backend forgot its registry — see registry/store.py's own
    'a restart honestly forgets' note).

    Called at startup AND on every successful (re)connect below — a dropped
    WS connection can silently lose events in the gap, and this is the only
    way to recover from that instead of drifting forever.
    """
    assert _client is not None
    resp = await _client.get("/api/drivers")
    resp.raise_for_status()
    seen: set[str] = set()
    for data in resp.json():
        record = DriverRecord.model_validate(data)
        seen.add(record.slug)
        _arm(record)
    for slug in list(_armed):
        if slug not in seen:
            _remove_armed(slug)


async def _refresh_one(slug: str) -> None:
    """Re-fetch one driver and reconcile — the shared path for both driver.* events."""
    assert _client is not None
    resp = await _client.get(f"/api/drivers/{slug}")
    if resp.status_code == 200:
        _arm(DriverRecord.model_validate(resp.json()))
    elif resp.status_code == 404:
        _remove_armed(slug)


async def _listen_ws() -> None:
    """Mirror driver.registered/driver.updated into the MCP tool set, live.

    Every successful connect (including reconnects) runs a full
    _reconcile_all() first — the WS stream is a freshness optimization on
    top of that, never the only source of truth. A single malformed/
    unexpected frame is logged and skipped, not fatal: only a dropped
    connection breaks out to the reconnect loop.
    """
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                logger.info("mcp: connected to %s", WS_URL)
                await _reconcile_all()
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                        if event.get("type") in ("driver.registered", "driver.updated"):
                            await _refresh_one(event["payload"]["slug"])
                    except Exception:  # noqa: BLE001 — one bad frame must not kill the listener
                        logger.warning("mcp: skipping unparseable/unexpected frame: %r", raw[:200])
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            logger.warning("mcp: ws connection lost (%s) — retrying in 3s", exc)
            await asyncio.sleep(3)


async def main() -> None:
    global _client
    if not TOKEN:
        logger.warning(
            "SELFAWARE_MCP_TOKEN is unset — the backend's read/set endpoints will refuse every "
            "call (403), so every tool call will fail until it's set on BOTH processes."
        )
    _client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=10.0)
    try:
        await _reconcile_all()
        ws_task = asyncio.create_task(_listen_ws())
        try:
            await mcp.run_async(transport="http", host=HOST, port=PORT)
        finally:
            ws_task.cancel()
    finally:
        await _client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
