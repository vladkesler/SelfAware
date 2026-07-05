"""/ws end-to-end against the real app factory: hello-first, full mock
commission theater, and a malformed frame that does NOT kill the socket.

Runs the ENTIRE stack (lifespan, MockBoard + demo script, mock author,
CommissionRunner, registry) with zero hardware and zero keys — this is
`make demo-mock` as a test."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from selfaware.api.app import create_app
from selfaware.config import Settings

MAX_FRAMES = 300  # hard cap so a broken stream fails the test instead of hanging it


def _settings() -> Settings:
    # mock_pace_s=0: theatrical demo pacing must never slow the suite.
    return Settings(_env_file=None, mock_board=True, mock_author=True, poller_interval_s=60.0, mock_pace_s=0.0)


def _drain_until(ws, event_type: str) -> list[dict]:
    """Receive frames until `event_type` arrives; returns everything seen."""
    seen: list[dict] = []
    for _ in range(MAX_FRAMES):
        frame = ws.receive_json()
        seen.append(frame)
        if frame["type"] == event_type:
            return seen
    raise AssertionError(f"never saw {event_type}; got {[f['type'] for f in seen]}")


def test_hello_then_full_mock_commission_then_bad_frame_survives() -> None:
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        # -- 1. hello is the FIRST frame, per protocol -------------------------
        hello = ws.receive_json()
        assert hello["type"] == "system.hello"
        assert hello["payload"]["protocol_v"] == 1
        assert hello["payload"]["board"]["connected"] is True
        assert hello["payload"]["board"]["mock"] is True  # badged, never silent
        assert hello["payload"]["drivers"] == []

        # -- 2. one command, the whole theater ---------------------------------
        cmd_id = str(uuid4())
        ws.send_json({"type": "cmd.commission", "id": cmd_id, "payload": {"preset_slug": "ldr"}})
        frames = _drain_until(ws, "commission.passed")
        types = [f["type"] for f in frames]

        assert "system.ack" in types
        acks = [f for f in frames if f["type"] == "system.ack"]
        assert acks[0]["payload"]["cmd_id"] == cmd_id
        assert "commission.started" in types
        assert "commission.traceback" in types  # the demo's verbatim board error
        assert "driver.registered" in types
        # traceback precedes registration precedes passed: the story is in order
        assert types.index("commission.traceback") < types.index("driver.registered")

        # the agent's actual work is on the wire: reasoning + verbatim code
        assert "agent.thought" in types
        assert "commission.code" in types
        assert types.index("agent.thought") < types.index("commission.code")
        thoughts = [f["payload"] for f in frames if f["type"] == "agent.thought"]
        # AUTHOR writes the first draft; MEDIC repairs from the verbatim traceback.
        assert [t["agent"] for t in thoughts] == ["author", "medic"]
        codes = [f["payload"] for f in frames if f["type"] == "commission.code"]
        assert [c["attempt"] for c in codes] == [1, 2]
        assert [c["is_repair"] for c in codes] == [False, True]
        # e2e proof of the demo story: the ESP32 habit, then the repair
        assert "adc.read()" in codes[0]["code"]
        assert "read_u16" not in codes[0]["code"]
        assert "read_u16" in codes[1]["code"]
        passed = frames[-1]["payload"]
        assert passed["slug"] == "ldr"
        assert passed["attempts_used"] == 2  # fail -> repair -> pass, per the demo script

        # seq is monotonic across everything the bus stamped (hello is seq=0)
        seqs = [f["seq"] for f in frames]
        assert seqs == sorted(seqs)

        # -- 3. malformed frame -> system.error, socket stays alive -------------
        ws.send_text("this is not an envelope {")
        frames = _drain_until(ws, "system.error")
        assert frames[-1]["payload"]["code"] == "malformed_command"

        # socket still works — and the mock scan finds the known I2C bricks,
        # so the discovery beat demos keyless too
        ws.send_json({"type": "cmd.board_scan", "id": str(uuid4()), "payload": {}})
        frames = _drain_until(ws, "discovery.device_found")
        found = frames[-1]["payload"]
        assert found["bus"] == "i2c"
        assert found["confidence"] == "exact"
        assert found["identity"]  # KNOWN_I2C_DEVICES matched (0x3C or 0x70)


def test_unknown_preset_is_a_named_error() -> None:
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "system.hello"
        cmd_id = str(uuid4())
        ws.send_json({"type": "cmd.commission", "id": cmd_id, "payload": {"preset_slug": "flux_capacitor"}})
        frames = _drain_until(ws, "system.error")
        error = frames[-1]["payload"]
        assert error["code"] == "unknown_preset"
        assert error["cmd_id"] == cmd_id


def test_chat_without_key_is_a_named_model_unavailable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Degradation matrix: no key + real model -> one clean system.error,
    never a crash and never a silent mock."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "system.hello"
        cmd_id = str(uuid4())
        ws.send_json({"type": "cmd.chat", "id": cmd_id, "payload": {"text": "hello?"}})
        frames = _drain_until(ws, "system.error")
        error = frames[-1]["payload"]
        assert error["code"] == "model_unavailable"
        assert error["cmd_id"] == cmd_id
        assert "ANTHROPIC_API_KEY" in error["message"]


def test_stimulate_is_mock_only_but_works_on_mock() -> None:
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "system.hello"
        ws.send_json({"type": "cmd.stimulate", "id": str(uuid4()), "payload": {"slug": "ldr", "delta": 5000}})
        frames = _drain_until(ws, "system.ack")  # accepted on the mock board
        assert frames[-1]["type"] == "system.ack"
