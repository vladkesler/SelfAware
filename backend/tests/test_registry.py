"""DriverRegistry: admission emits the flat wire event; hot-swap emits driver.updated."""

import pytest

from selfaware.events.bus import EventBus
from selfaware.events.payloads import DriverSummary
from selfaware.events.types import DriverStatus, ProtocolClass
from selfaware.registry.models import DriverRecord
from selfaware.registry.store import DriverRegistry, code_hash

from tests.conftest import BusSpy

CODE_V1 = "class Driver:\n    def read(self):\n        return 1\n"
CODE_V2 = "class Driver:\n    def read(self):\n        return 2\n"


def _record(**overrides: object) -> DriverRecord:
    fields: dict = {
        "slug": "ldr",
        "display_name": "Light sensor",
        "protocol_class": ProtocolClass.ANALOG,
        "driver_code": CODE_V1,
        "pins": {"adc": 27},
        "unit": "raw",
        "status": DriverStatus.ACTIVE,
        "last_reading": 32000.0,
    }
    fields.update(overrides)
    return DriverRecord(**fields)


def test_register_emits_flat_driver_registered(bus: EventBus, bus_spy: BusSpy) -> None:
    registry = DriverRegistry(bus)
    registry.register(_record())

    events = bus_spy.of_type("driver.registered")
    assert len(events) == 1
    payload = events[0].payload
    assert payload["slug"] == "ldr"
    assert payload["protocol_class"] == "analog"
    assert payload["pins"] == {"adc": 27}
    assert payload["tool_names"] == ["read_ldr"]
    assert payload["code_hash"] == code_hash(CODE_V1)
    assert len(payload["code_hash"]) == 12


def test_summary_conversion_matches_wire_model(bus: EventBus) -> None:
    record = _record()
    summary = record.summary()
    assert isinstance(summary, DriverSummary)  # THE events.payloads model, not a twin
    assert summary.slug == "ldr"
    assert summary.status is DriverStatus.ACTIVE
    assert summary.last_reading == 32000.0

    registry = DriverRegistry(bus)
    registry.register(record)
    assert registry.summaries() == [summary]


def test_update_code_changes_hash_and_emits_driver_updated(bus: EventBus, bus_spy: BusSpy) -> None:
    registry = DriverRegistry(bus)
    registry.register(_record())
    bus_spy.drain()

    registry.update_code("ldr", CODE_V2, reason="repair")

    record = registry.get("ldr")
    assert record is not None
    assert record.driver_code == CODE_V2
    assert record.verified_at is not None

    events = bus_spy.of_type("driver.updated")
    assert len(events) == 1
    assert events[0].payload["code_hash"] == code_hash(CODE_V2)
    assert events[0].payload["code_hash"] != code_hash(CODE_V1)
    assert events[0].payload["reason"] == "repair"


def test_update_code_refuses_unregistered_slug(bus: EventBus) -> None:
    registry = DriverRegistry(bus)
    with pytest.raises(KeyError):
        registry.update_code("ghost", CODE_V1)


def test_sensors_and_actuators_split_on_class_and_status(bus: EventBus) -> None:
    registry = DriverRegistry(bus)
    registry.register(_record())
    registry.register(
        _record(slug="buzzer", protocol_class=ProtocolClass.OUTPUT, pins={"pwm": 20}, unit="")
    )
    registry.register(_record(slug="dead", status=DriverStatus.FAILED))

    assert [r.slug for r in registry.sensors()] == ["ldr"]
    assert [r.slug for r in registry.actuators()] == ["buzzer"]
    assert registry.get("buzzer").tool_names == ["set_buzzer"]
