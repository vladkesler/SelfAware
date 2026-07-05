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

STATIC_TOOLS = {
    "list_capabilities",
    "read_sensor",
    "get_sensor_health",
    "list_commissionable_devices",
    "probe_bus",
    "commission_device",
    "get_commission_status",
    "set_actuator",
    "get_sensor_history",
    "get_driver_code",
    "display_message",
}

SCAN_RESULT: dict[str, Any] = {
    "addresses": [60, 112],
    "matches": [
        {"addr": 112, "addr_hex": "0x70", "identity": "SHTC3", "confidence": "exact", "preset_slug": "shtc3"},
        {"addr": 60, "addr_hex": "0x3c", "identity": "SSD1306", "confidence": "exact", "preset_slug": None},
    ],
    "note": "live scan taken at call time",
}

COMMISSION_PASSED: dict[str, Any] = {
    "commission_id": "c1",
    "slug": "ldr",
    "display_name": "Light sensor",
    "status": "passed",
    "attempts_used": 2,
    "final_reading": 42.0,
    "unit": "raw",
    "failure_reason": None,
    "attempts": [],
    "tool": "read_ldr",
}


@pytest.fixture
def backend(monkeypatch):
    """A scriptable fake backend: mutate state['drivers'] between requests to
    simulate commissions/demotions — no arming or de-arming calls exist to
    make, which is exactly the property under test."""
    state: dict[str, Any] = {
        "drivers": [],
        "reads": [],
        "sets": [],
        "fail_listing": False,
        "busy": False,
        "polls_until_done": 0,
        "status_polls": 0,
        "said": [],
    }

    def _authed(request: httpx.Request) -> bool:
        return request.headers.get("authorization") == f"Bearer {TOKEN}"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/drivers":
            if state["fail_listing"]:
                return httpx.Response(500, json={"detail": "backend on fire"})
            return httpx.Response(200, json=state["drivers"])
        if path == "/api/board":
            return httpx.Response(200, json={"connected": True, "mock": True})
        if path == "/api/presets":
            return httpx.Response(200, json={"presets": state.get("presets", [])})
        if path == "/api/board/scan":
            if not _authed(request):
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            return httpx.Response(200, json=SCAN_RESULT)
        if path == "/api/commission":
            if not _authed(request):
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            if state["busy"]:
                return httpx.Response(409, json={"detail": "commission_busy: a commission is already running"})
            return httpx.Response(
                202, json={"commission_id": "c1", "slug": "ldr", "status": "running", "max_attempts": 4}
            )
        if path == "/api/commission/c1":
            state["status_polls"] += 1
            if state["status_polls"] <= state["polls_until_done"]:
                return httpx.Response(200, json={"commission_id": "c1", "slug": "ldr", "status": "running"})
            return httpx.Response(200, json=COMMISSION_PASSED)
        if path == "/api/oled/say":
            if not _authed(request):
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            state["said"].append(request.content.decode())
            return httpx.Response(200, json={"ok": True, "text": "hi", "note": "queued"})
        if path.startswith("/api/drivers/") and path.endswith("/read"):
            slug = path.split("/")[3]
            if not _authed(request):
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            if not any(d["slug"] == slug and d["status"] == "active" for d in state["drivers"]):
                return httpx.Response(404, json={"detail": f"no driver registered for {slug!r}"})
            state["reads"].append(slug)
            return httpx.Response(
                200, json={"slug": slug, "value": 512.0, "unit": "raw", "read_at": "2026-07-05T00:00:00Z"}
            )
        if path.startswith("/api/drivers/") and path.endswith("/set"):
            slug = path.split("/")[3]
            if not _authed(request):
                return httpx.Response(401, json={"detail": "missing or invalid bearer token"})
            if not any(d["slug"] == slug and d["status"] == "active" for d in state["drivers"]):
                return httpx.Response(404, json={"detail": f"no driver registered for {slug!r}"})
            state["sets"].append(slug)
            return httpx.Response(200, json={"slug": slug, "level": 1.0, "ok": True})
        if path.startswith("/api/drivers/") and path.endswith("/health"):
            slug = path.split("/")[3]
            return httpx.Response(200, json={"slug": slug, "status": "healthy", "reasons": []})
        if path.startswith("/api/drivers/") and path.endswith("/history"):
            slug = path.split("/")[3]
            return httpx.Response(200, json={"slug": slug, "unit": "raw", "points": [[1.0, 500.0], [2.0, 512.0]]})
        if path.startswith("/api/drivers/"):
            slug = path.split("/")[3]
            record = next((d for d in state["drivers"] if d["slug"] == slug), None)
            if record is None:
                return httpx.Response(404, json={"detail": f"no driver registered for {slug!r}"})
            return httpx.Response(200, json=record)
        return httpx.Response(404, json={"detail": "nope"})

    monkeypatch.setattr(
        mcp_server, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")
    )
    monkeypatch.setattr(mcp_server, "TOKEN", TOKEN)
    monkeypatch.setattr(mcp_server, "COMMISSION_POLL_S", 0.0)
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


# --- the commissioning/discovery surface --------------------------------------


async def test_commission_device_polls_to_terminal_and_returns_attempts(backend) -> None:
    """The one-call happy path: POST 202, poll to terminal, return the full
    outcome — the mock/demo pace fits inside a single tool call."""
    backend["polls_until_done"] = 2
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("commission_device", {"preset_slug": "ldr"})
    assert result.data["status"] == "passed"
    assert result.data["attempts_used"] == 2
    assert result.data["tool"] == "read_ldr"
    assert backend["status_polls"] == 3  # 2 running + 1 terminal, not one more


async def test_commission_device_budget_exhausted_returns_running_not_error(backend, monkeypatch) -> None:
    """A slow real commission must degrade to an honest 'still running' with
    the commission_id — never a client-side timeout that loses the handle."""
    monkeypatch.setattr(mcp_server, "COMMISSION_WAIT_S", 0.0)
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("commission_device", {"preset_slug": "ldr"})
    assert result.data["status"] == "running"
    assert result.data["commission_id"] == "c1"
    assert "get_commission_status" in result.data["note"]


async def test_commission_device_busy_is_a_named_error(backend) -> None:
    backend["busy"] = True
    async with Client(mcp_server.mcp) as client:
        with pytest.raises(Exception, match="commission_busy"):
            await client.call_tool("commission_device", {"preset_slug": "ldr"})


async def test_get_commission_status_passes_outcome_through(backend) -> None:
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_commission_status", {"commission_id": "c1"})
    assert result.data["status"] == "passed"
    assert result.data["attempts_used"] == 2


async def test_probe_bus_hits_token_gated_seam(backend) -> None:
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("probe_bus", {})
    assert result.data["addresses"] == [60, 112]
    assert result.data["matches"][0]["preset_slug"] == "shtc3"


async def test_list_commissionable_devices_passthrough(backend) -> None:
    backend["presets"] = [{"slug": "ldr", "commissioned": False}]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_commissionable_devices", {})
    assert result.data["presets"][0]["slug"] == "ldr"


async def test_set_actuator_gateway_drives_a_slug_the_session_never_listed(backend) -> None:
    """The set-side twin of the read_sensor gateway: an actuator commissioned
    mid-session is drivable with no re-list."""
    backend["drivers"] = []
    async with Client(mcp_server.mcp) as client:
        await client.list_tools()  # session's view: no dynamic tools
        backend["drivers"] = [SERVO]  # commissioned mid-session
        result = await client.call_tool("set_actuator", {"slug": "servo", "level": 1.0})
    assert backend["sets"] == ["servo"]
    assert result.data["ok"] is True


async def test_get_sensor_history_carries_not_live_note(backend) -> None:
    backend["drivers"] = [LDR]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_sensor_history", {"slug": "ldr"})
    assert result.data["points"] == [[1.0, 500.0], [2.0, 512.0]]
    assert "not a live reading" in result.data["note"]


async def test_get_driver_code_returns_source_with_provenance(backend) -> None:
    backend["drivers"] = [{**LDR, "attempts_used": 2}]
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_driver_code", {"slug": "ldr"})
    assert result.data["driver_code"] == "class Driver: ..."
    assert result.data["attempts_used"] == 2


async def test_display_message_posts_to_oled_seam(backend) -> None:
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("display_message", {"text": "HELLO"})
    assert result.data["ok"] is True
    assert backend["said"] and "HELLO" in backend["said"][0]


async def test_new_tool_annotations(backend) -> None:
    """readOnlyHint on everything that only observes; absent on everything
    that commissions, actuates, or draws."""
    async with Client(mcp_server.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    read_only = {"list_commissionable_devices", "probe_bus", "get_commission_status", "get_sensor_history", "get_driver_code"}
    for name in read_only:
        assert tools[name].annotations.readOnlyHint is True, name
    for name in ("commission_device", "set_actuator", "display_message"):
        assert tools[name].annotations is None or tools[name].annotations.readOnlyHint is not True, name
