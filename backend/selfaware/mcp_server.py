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
belongs to the main backend process alone. Instead it holds NO tool state at
all: RegistryProvider below resolves the tool list against
`GET /api/drivers` on every MCP request, so the armed tool set is exactly
the registry's ACTIVE set at the moment a client asks — the same
resolve-at-call-time invariant the copilot's in-process toolset has
(registry/store.py::as_toolset). There is nothing to reconcile and nothing
that can drift: a re-commission, a repair that flips read<->set, or a driver
demoted out of ACTIVE is simply reflected in the next request's answer.

The actual hardware calls go through POST /api/drivers/{slug}/read and /set,
bearer-authenticated (api/rest.py::require_mcp_token, fails closed when
SELFAWARE_MCP_TOKEN is unset). Records are parsed into the real
DriverRecord/ProtocolClass/DriverStatus types, so this file shares the exact
tool-description wording and protocol-class enum the in-process copilot
toolset uses (registry/models.py::DriverRecord.read_description/
set_description) — no second, hand-written copy to drift out of sync.

Known limitation, stated plainly: fastmcp only pushes tools/list_changed
from inside an active request context, so a sensor commissioned while an
MCP client's session is open will NOT appear in that session's tool list
until the client re-lists (e.g. Claude Code's /mcp -> reconnect). The
static `read_sensor` gateway tool below exists precisely for that gap — it
is always present, so a freshly commissioned slug is usable immediately via
list_capabilities -> read_sensor, no reconnect required.

Honesty floor for callers we don't control: every tool description and every
response payload says the reading is live, taken at call time — since an
external agent's own system prompt is outside our control, the guardrail has
to travel with the data, not depend on the caller's instructions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.providers import Provider
from fastmcp.tools.function_tool import FunctionTool
from mcp.types import ToolAnnotations

from selfaware.registry.models import DriverRecord, DriverStatus, ProtocolClass

logger = logging.getLogger("selfaware.mcp_server")

BACKEND_URL = os.environ.get("SELFAWARE_MCP_BACKEND_URL", "http://localhost:8000")
TOKEN = os.environ.get("SELFAWARE_MCP_TOKEN", "")
HOST = os.environ.get("SELFAWARE_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("SELFAWARE_MCP_PORT", "8001"))

_client: httpx.AsyncClient | None = None

_LIVE_NOTE = "live reading, taken at call time — re-call for the current value, do not cache"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


async def _read_slug(slug: str) -> dict[str, Any]:
    """One live reading through the backend's token-gated seam — shared by the
    dynamic read_<slug> tools and the static read_sensor gateway."""
    assert _client is not None
    resp = await _client.post(f"/api/drivers/{slug}/read", headers=_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"read_{slug}: backend said {resp.status_code} — {resp.text}")
    data = resp.json()
    return {
        "value": data["value"],
        "unit": data.get("unit", ""),
        "read_at": data.get("read_at"),
        "note": _LIVE_NOTE,
    }


def _make_read_tool(slug: str):
    async def read_tool() -> dict[str, Any]:
        return await _read_slug(slug)

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


class RegistryProvider(Provider):
    """Tool list = the registry's ACTIVE set, fetched fresh per MCP request.

    Stateless on purpose: the earlier design mirrored the registry through a
    WebSocket listener plus reconciliation passes, which meant local state
    that could drift (and a background task whose death silently froze the
    tool set). Resolving per-request deletes that failure class — the cost is
    one loopback GET per tools/list, which is nothing next to a serial-port
    hardware read. Tool CALLS resolve through this same path (fastmcp's
    default get_tool searches _list_tools), so a de-commissioned driver's
    tool call fails with a clean not-found instead of running against a
    stale record.
    """

    async def _list_tools(self) -> list[FunctionTool]:
        assert _client is not None
        resp = await _client.get("/api/drivers")
        resp.raise_for_status()  # backend down/unhappy -> clean MCP error for this request, server stays up
        tools: list[FunctionTool] = []
        for data in resp.json():
            record = DriverRecord.model_validate(data)
            if record.status is not DriverStatus.ACTIVE:
                continue  # admission gate: only silicon-verified drivers arm tools
            if record.protocol_class is ProtocolClass.OUTPUT:
                tools.append(
                    FunctionTool.from_function(
                        _make_set_tool(record.slug),
                        name=f"set_{record.slug}",
                        description=record.set_description(),
                    )
                )
            else:
                tools.append(
                    FunctionTool.from_function(
                        _make_read_tool(record.slug),
                        name=f"read_{record.slug}",
                        description=record.read_description(),
                        annotations=ToolAnnotations(readOnlyHint=True),
                    )
                )
        return tools


mcp: FastMCP = FastMCP("SelfAware", providers=[RegistryProvider()])


# --- static tools: present from t=0, no commissioning required ---------------
# These are the discovery/fallback surface for agents that connected before
# any driver existed (or while one is being commissioned mid-session).


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_capabilities() -> dict[str, Any]:
    """What this bench can do right now: board connection status plus every
    commissioned driver (its slug, kind, status, unit, last reading, and the
    exact tool that drives it). Call this first to discover what exists."""
    assert _client is not None
    board_resp = await _client.get("/api/board")
    board_resp.raise_for_status()
    drivers_resp = await _client.get("/api/drivers")
    drivers_resp.raise_for_status()
    drivers = []
    for data in drivers_resp.json():
        record = DriverRecord.model_validate(data)
        drivers.append(
            {
                "slug": record.slug,
                "display_name": record.display_name,
                "protocol_class": record.protocol_class.value,
                "status": record.status.value,
                "unit": record.unit,
                "last_reading": record.last_reading,
                "last_read_at": record.last_read_at,
                "tool": record.tool_names[0],
            }
        )
    return {"board": board_resp.json(), "drivers": drivers, "note": "snapshot taken at call time"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def read_sensor(slug: str) -> dict[str, Any]:
    """Take a live reading from any commissioned sensor by slug. Same verified
    driver and hardware lock as the per-sensor read_<slug> tools — use this
    when a sensor was commissioned after your session's tool list was built
    (find slugs via list_capabilities)."""
    result = await _read_slug(slug)
    return {"slug": slug, **result}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_sensor_health(slug: str) -> dict[str, Any]:
    """Health verdict for a commissioned sensor: healthy/degrading/critical
    with the NAMED reason (staleness, railing, variance, baseline drift),
    computed from real accumulated readings only — never a bare score."""
    assert _client is not None
    resp = await _client.get(f"/api/drivers/{slug}/health")
    if resp.status_code != 200:
        raise RuntimeError(f"get_sensor_health({slug!r}): backend said {resp.status_code} — {resp.text}")
    return resp.json()


async def main() -> None:
    global _client
    if not TOKEN:
        logger.warning(
            "SELFAWARE_MCP_TOKEN is unset — the backend's read/set endpoints will refuse every "
            "call (403), so every read/set tool call will fail until it's set on BOTH processes."
        )
    _client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=10.0)
    try:
        await mcp.run_async(transport="http", host=HOST, port=PORT)
    finally:
        await _client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
