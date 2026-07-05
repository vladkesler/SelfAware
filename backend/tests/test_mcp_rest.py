"""The MCP transport's network seam: /api/drivers/{slug}/read and /set.

mcp_server.py never touches BoardSession directly — it calls these two
endpoints over HTTP, so this is where the auth-fails-closed contract and the
single-lock-under-concurrent-callers contract actually get exercised. See
mcp_server.py and api/rest.py for the design ("why a separate process, why a
bearer token, why re-fetch on every driver.* event").
"""

import asyncio
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from selfaware.api.app import create_app
from selfaware.config import Settings
from selfaware.registry.models import DriverRecord, DriverStatus, ProtocolClass

TOKEN = "test-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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


# --- POST /api/commission + GET /api/commission/{id} --------------------------


def _poll_commission(client: TestClient, commission_id: str, timeout_s: float = 10.0) -> dict:
    """Poll the status endpoint until terminal. TestClient's portal keeps the
    app's event loop running in a background thread, so the commission task
    progresses while this thread sleeps."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/api/commission/{commission_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("commission never reached a terminal state")


def test_commission_endpoint_fails_closed_without_token() -> None:
    app = create_app(_settings())  # mcp_token defaults to "" — not configured
    with TestClient(app) as client:
        assert client.post("/api/commission", json={"preset_slug": "ldr"}).status_code == 403


def test_commission_endpoint_rejects_wrong_token() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        resp = client.post(
            "/api/commission", json={"preset_slug": "ldr"}, headers={"Authorization": "Bearer wrong"}
        )
        assert resp.status_code == 401


def test_commission_endpoint_runs_to_passed_status() -> None:
    """The full arc over REST alone: 202 with a poll URL, the mock author's
    canned fail->repair->pass, a terminal outcome with the honest attempt
    count, and a now-ACTIVE driver."""
    app = create_app(_settings(mcp_token=TOKEN, mock_pace_s=0.0))
    with TestClient(app) as client:
        resp = client.post("/api/commission", json={"preset_slug": "ldr"}, headers=AUTH)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "running"
        outcome = _poll_commission(client, body["commission_id"])
        assert outcome["status"] == "passed"
        assert outcome["attempts_used"] == 2  # the canned arc: fail, then repair
        assert outcome["tool"] == "read_ldr"
        assert outcome["attempts"][0]["passed"] is False
        driver = client.get("/api/drivers/ldr")
        assert driver.status_code == 200
        assert driver.json()["status"] == "active"


def test_second_commission_while_running_is_409() -> None:
    app = create_app(_settings(mcp_token=TOKEN, mock_pace_s=0.3))
    with TestClient(app) as client:
        first = client.post("/api/commission", json={"preset_slug": "ldr"}, headers=AUTH)
        assert first.status_code == 202
        second = client.post("/api/commission", json={"preset_slug": "pot"}, headers=AUTH)
        assert second.status_code == 409
        assert "commission_busy" in second.json()["detail"]
        _poll_commission(client, first.json()["commission_id"])  # drain before shutdown


def test_unknown_preset_is_422() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        resp = client.post("/api/commission", json={"preset_slug": "no_such"}, headers=AUTH)
        assert resp.status_code == 422
        assert "unknown_preset" in resp.json()["detail"]


def test_unknown_commission_id_is_404() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        assert client.get("/api/commission/nope").status_code == 404


# --- POST /api/board/scan ------------------------------------------------------


def test_board_scan_endpoint_finds_known_bricks() -> None:
    """MockBoard's persistent scan responder answers [0x3C, 0x70]; the 0x70
    match must carry the shtc3 preset_slug for one-call commission routing."""
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        assert client.post("/api/board/scan").status_code == 401  # no creds, token configured
        resp = client.post("/api/board/scan", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert body["addresses"] == [60, 112]
        by_addr = {m["addr"]: m for m in body["matches"]}
        assert by_addr[112]["preset_slug"] == "shtc3"
        assert by_addr[112]["confidence"] == "exact"
        assert by_addr[60]["addr_hex"] == "0x3c"


# --- GET /api/presets ------------------------------------------------------------


def test_presets_annotated_with_commissioned() -> None:
    app = create_app(_settings(mcp_token=TOKEN, mock_pace_s=0.0))
    with TestClient(app) as client:
        before = {p["slug"]: p for p in client.get("/api/presets").json()["presets"]}
        assert set(before) >= {"ldr", "pot", "shtc3", "ultrasonic", "buzzer", "fan", "servo"}
        assert all(not p["commissioned"] for p in before.values())
        assert before["buzzer"]["tool"] == "set_buzzer"
        assert "extra_context" not in before["fan"]  # prompt plumbing must not leak

        with client.websocket_connect("/ws") as ws:
            _commission_ldr(ws)
        after = {p["slug"]: p for p in client.get("/api/presets").json()["presets"]}
        assert after["ldr"]["commissioned"] is True
        assert after["ldr"]["driver_status"] == "active"


# --- POST /api/oled/say ----------------------------------------------------------


def test_oled_say_is_token_gated_and_queues() -> None:
    app = create_app(_settings(mcp_token=TOKEN))
    with TestClient(app) as client:
        assert client.post("/api/oled/say", json={"text": "HI"}).status_code == 401  # no creds, token configured
        resp = client.post("/api/oled/say", json={"text": "HELLO FROM CLAUDE"}, headers=AUTH)
        # 200 (narrator up, mock board answers draws) or honest 409 — never a crash
        assert resp.status_code in (200, 409)
        if resp.status_code == 200:
            assert resp.json()["ok"] is True
