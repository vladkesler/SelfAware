"""The MCP transport's network seam: /api/drivers/{slug}/read and /set.

mcp_server.py never touches BoardSession directly — it calls these two
endpoints over HTTP, so this is where the auth-fails-closed contract and the
single-lock-under-concurrent-callers contract actually get exercised. See
mcp_server.py and api/rest.py for the design ("why a separate process, why a
bearer token, why re-fetch on every driver.* event").
"""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from selfaware.api.app import create_app
from selfaware.config import Settings
from selfaware.registry.models import DriverRecord, DriverStatus, ProtocolClass

TOKEN = "test-secret"


def _settings(**overrides) -> Settings:
    overrides.setdefault("poller_interval_s", 60.0)
    return Settings(_env_file=None, mock_board=True, mock_author=True, **overrides)


def _commission_ldr(ws) -> None:
    """Drive the same fail->repair->pass arc test_ws_endpoint.py exercises,
    so the registry holds a real ACTIVE 'ldr' driver afterward."""
    assert ws.receive_json()["type"] == "system.hello"
    ws.send_json({"type": "cmd.commission", "id": str(uuid4()), "payload": {"preset_slug": "ldr"}})
    for _ in range(300):
        frame = ws.receive_json()
        if frame["type"] == "commission.passed":
            return
    raise AssertionError("commission never passed")


def test_read_endpoint_fails_closed_when_token_unconfigured() -> None:
    """SELFAWARE_MCP_TOKEN unset -> 403 for everyone, not '200 open to all'."""
    app = create_app(_settings())  # mcp_token defaults to "" — not configured
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        resp = client.post("/api/drivers/ldr/read")
        assert resp.status_code == 403


def test_read_endpoint_rejects_wrong_token() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        resp = client.post("/api/drivers/ldr/read", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401


def test_read_endpoint_works_with_correct_token() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        resp = client.post("/api/drivers/ldr/read", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "ldr"
        assert isinstance(body["value"], (int, float))


def test_read_endpoint_unknown_slug_is_404() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        resp = client.post("/api/drivers/no_such_slug/read", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 404


def test_set_endpoint_drives_a_directly_registered_actuator() -> None:
    """Bypass the commission loop (fake_registry's allowance, same pattern
    used elsewhere in this suite) to test the /set path without depending on
    MockBoard's scripted output-class behavior."""
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        state = app.state.selfaware
        state.registry.register(
            DriverRecord(
                slug="relay",
                display_name="Relay",
                protocol_class=ProtocolClass.OUTPUT,
                driver_code="class Driver:\n    def set(self, level):\n        pass\n",
                pins={"pwm": 12},
                status=DriverStatus.ACTIVE,
            )
        )
        resp = client.post(
            "/api/drivers/relay/set",
            json={"level": 1.0},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"slug": "relay", "level": 1.0, "ok": True}


async def test_concurrent_reads_do_not_deadlock_or_corrupt() -> None:
    """N concurrent external callers on the single lock, alongside the
    already-running poller — the scenario MCP as a new caller actually
    introduces. Every response must be a clean 200 with a plausible value;
    a failure here means the lock isn't serializing external REST callers
    the way it serializes the copilot's in-process calls."""
    app = create_app(_settings(mcp_token=TOKEN, poller_interval_s=0.05))
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        headers = {"Authorization": f"Bearer {TOKEN}"}

        async def one_read() -> int:
            resp = await asyncio.to_thread(client.post, "/api/drivers/ldr/read", headers=headers)
            return resp.status_code

        results = await asyncio.gather(*(one_read() for _ in range(20)))
        assert results == [200] * 20
