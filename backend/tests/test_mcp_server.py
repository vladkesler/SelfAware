"""mcp_server.py's provider logic, exercised without a network or a backend.

The design under test is the ABSENCE of state: RegistryProvider resolves the
tool list against GET /api/drivers on every request, so "a driver appeared/
vanished/flipped class/left ACTIVE" are not lifecycle events to reconcile —
they're just different answers on the next request. These tests swap the
module's httpx client for a MockTransport-backed one and talk to the server
through fastmcp's in-memory Client, the same path a real MCP client takes.

The REST seam itself (auth fails closed, the single lock under concurrency)
is covered separately in test_mcp_rest.py against the real FastAPI app.
"""

from typing import Any

import httpx
import pytest
from fastmcp import Client

import selfaware.mcp_server as mcp_server

TOKEN = "test-secret"

LDR: dict[str, Any] = {
    "slug": "ldr",
    "display_name": "Light sensor",
    "protocol_class": "analog",
    "driver_code": "class Driver: ...",
    "pins": {"adc": 27},
    "unit": "raw",
    "status": "active",
}
SERVO: dict[str, Any] = {
    "slug": "servo",
    "display_name": "Servo",
    "protocol_class": "output",
    "driver_code": "class Driver: ...",
    "pins": {"pwm": 21},
    "unit": "",
    "status": "active",
}
DEAD: dict[str, Any] = {**LDR, "slug": "dead", "display_name": "Failed sensor", "status": "failed"}

STATIC_TOOLS = {"list_capabilities", "read_sensor", "get_sensor_health"}


@pytest.fixture
def backend(monkeypatch):
    """A scriptable fake backend: mutate state['drivers'] between requests to
    simulate commissions/demotions — no arming or de-arming calls exist to
    make, which is exactly the property under test."""
    state: dict[str, Any] = {"drivers": [], "reads": [], "fail_listing": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/drivers":
            if state["fail_listing"]:
                return httpx.Response(500, json={"detail": "backend on fire"})
            return httpx.Response(200, json=state["drivers"])
        if path == "/api/board":
            return httpx.Response(200, json={"connected": True, "mock": True})
        if path.startswith("/api/drivers/") and path.endswith("/read"):
            slug = path.split("/")[3]
            if request.headers.get("authorization") != f"Bearer {TOKEN}":
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            if not any(d["slug"] == slug and d["status"] == "active" for d in state["drivers"]):
                return httpx.Response(404, json={"detail": f"no driver registered for {slug!r}"})
            state["reads"].append(slug)
            return httpx.Response(
                200, json={"slug": slug, "value": 512.0, "unit": "raw", "read_at": "2026-07-05T00:00:00Z"}
            )
        if path.startswith("/api/drivers/") and path.endswith("/health"):
            slug = path.split("/")[3]
            return httpx.Response(200, json={"slug": slug, "status": "healthy", "reasons": []})
        return httpx.Response(404, json={"detail": "nope"})

    monkeypatch.setattr(
        mcp_server, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")
    )
    monkeypatch.setattr(mcp_server, "TOKEN", TOKEN)
    return state


async def _tool_names(client: Client) -> set[str]:
    return {t.name for t in await client.list_tools()}


async def test_arms_read_for_sensors_set_for_outputs_skips_non_active(backend) -> None:
    backend["drivers"] = [LDR, SERVO, DEAD]
    async with Client(mcp_server.mcp) as client:
        names = await _tool_names(client)
    assert names == STATIC_TOOLS | {"read_ldr", "set_servo"}
    assert "read_dead" not in names  # admission gate: FAILED never arms


async def test_registry_changes_reflect_on_next_list_without_any_lifecycle_code(backend) -> None:
    """Appear, flip protocol class, vanish — three registry changes, zero
    arming/de-arming calls, three correct answers."""
    backend["drivers"] = []
    async with Client(mcp_server.mcp) as client:
        assert await _tool_names(client) == STATIC_TOOLS

        backend["drivers"] = [LDR]
        assert await _tool_names(client) == STATIC_TOOLS | {"read_ldr"}

        backend["drivers"] = [{**LDR, "protocol_class": "output"}]  # repair flipped read -> set
        names = await _tool_names(client)
        assert names == STATIC_TOOLS | {"set_ldr"}
        assert "read_ldr" not in names  # no stale verb left behind

        backend["drivers"] = []
        assert await _tool_names(client) == STATIC_TOOLS


async def test_read_tool_hits_token_gated_seam_and_carries_liveness_note(backend) -> None:
    backend["drivers"] = [LDR]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("read_ldr", {})
    assert backend["reads"] == ["ldr"]
    assert result.data["value"] == 512.0
    assert result.data["note"] == mcp_server._LIVE_NOTE  # honesty travels with the data


async def test_read_annotated_read_only_set_not(backend) -> None:
    backend["drivers"] = [LDR, SERVO]
    async with Client(mcp_server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["read_ldr"].annotations.readOnlyHint is True
    assert tools["set_servo"].annotations is None


async def test_gateway_reads_a_sensor_the_session_never_listed(backend) -> None:
    """The mid-session-commission fallback: read_sensor works for a slug that
    appeared after the client's tool list was built, no re-list needed."""
    backend["drivers"] = []
    async with Client(mcp_server.mcp) as client:
        await client.list_tools()  # session's view: no dynamic tools
        backend["drivers"] = [LDR]  # commissioned mid-session
        result = await client.call_tool("read_sensor", {"slug": "ldr"})
    assert result.data["slug"] == "ldr"
    assert result.data["value"] == 512.0


async def test_backend_failure_degrades_one_request_not_the_server(backend) -> None:
    """Regression for the design this replaced: a backend 500 during listing
    must not kill or freeze anything — the old WS mirror died silently here
    and drifted forever. fastmcp's aggregate provider logs the failing
    provider and serves the rest, so the failure mode is 'static tools only
    for this request', then full recovery on the next one, same session."""
    backend["drivers"] = [LDR]
    async with Client(mcp_server.mcp) as client:
        backend["fail_listing"] = True
        assert await _tool_names(client) == STATIC_TOOLS  # degraded, not dead
        backend["fail_listing"] = False
        assert await _tool_names(client) == STATIC_TOOLS | {"read_ldr"}  # alive and correct


async def test_list_capabilities_reports_board_and_all_drivers_with_status(backend) -> None:
    backend["drivers"] = [LDR, DEAD]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_capabilities", {})
    data = result.data
    assert data["board"]["connected"] is True
    by_slug = {d["slug"]: d for d in data["drivers"]}
    assert by_slug["ldr"]["tool"] == "read_ldr"
    assert by_slug["dead"]["status"] == "failed"  # honest discovery: shown, with its status


async def test_get_sensor_health_passes_verdict_through(backend) -> None:
    backend["drivers"] = [LDR]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_sensor_health", {"slug": "ldr"})
    assert result.data["status"] == "healthy"
