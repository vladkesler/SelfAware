"""Envelope + payload round-trips: what goes over the wire must come back intact."""

import json
from uuid import uuid4

from selfaware.events.envelope import Command, Event
from selfaware.events.payloads import (
    CommissionCommand,
    CommissionStagePayload,
    HelloPayload,
    BoardStatusPayload,
)
from selfaware.events.types import CommandType, CommissionStage, EventType, StageStatus


def test_event_json_round_trip() -> None:
    payload = CommissionStagePayload(
        commission_id="c-1", attempt=2, stage=CommissionStage.REPAIR, status=StageStatus.STARTED
    )
    event = Event(type=EventType.COMMISSION_STAGE, ts="2026-07-04T12:00:00Z", seq=7, payload=payload.model_dump())
    wire = event.model_dump_json()
    back = Event.model_validate_json(wire)
    assert back == event
    assert CommissionStagePayload.model_validate(back.payload).stage is CommissionStage.REPAIR


def test_command_parses_from_client_json() -> None:
    cmd_id = uuid4()
    raw = json.dumps(
        {"type": "cmd.commission", "id": str(cmd_id), "payload": {"preset_slug": "ldr"}}
    )
    cmd = Command.model_validate_json(raw)
    assert cmd.type == CommandType.COMMISSION
    assert cmd.id == cmd_id
    assert CommissionCommand.model_validate(cmd.payload).preset_slug == "ldr"


def test_commission_command_accepts_full_spec_shape() -> None:
    body = CommissionCommand.model_validate(
        {
            "slug": "ultrasonic",
            "display_name": "Ultrasonic ranger",
            "protocol_class": "pulse_timing",
            "pins": {"trig": 14, "echo": 15},
            "expected_min": 2,
            "expected_max": 400,
            "unit": "cm",
        }
    )
    assert body.pins == {"trig": 14, "echo": 15}


def test_hello_rehydrates_with_unknown_extra_fields_ignored() -> None:
    """Forward-compat: a newer server adding payload fields must not break parsing."""
    hello = HelloPayload(
        server_version="0.1.0",
        protocol_v=1,
        board=BoardStatusPayload(connected=False),
        drivers=[],
    )
    data = hello.model_dump()
    data["board"]["future_field"] = "ignored"
    parsed = HelloPayload.model_validate(data)
    assert parsed.board.connected is False
