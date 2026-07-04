"""BoardSession: THE lock serializes, exclusive() pauses the poller, timeouts recover.

All against MockBoard — this is the layer that must work identically with
zero hardware.
"""

import asyncio

from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.types import DriverStatus, ProtocolClass
from selfaware.hardware.base import ExecResult
from selfaware.hardware.mock_board import MockBoard, ScriptedExchange
from selfaware.hardware.session import BoardSession
from selfaware.registry.models import DriverRecord
from selfaware.registry.store import DriverRegistry

from tests.conftest import BusSpy

# Driver code whose exec hits MockBoard's simulated ldr generator (ADC(27)).
LDR_DRIVER = "from machine import ADC\n\nclass Driver:\n    def read(self):\n        return ADC(27).read_u16()\n"


def _fast_settings() -> Settings:
    return Settings(_env_file=None, mock_board=True, poller_interval_s=0.01)


def _ldr_record() -> DriverRecord:
    return DriverRecord(
        slug="ldr",
        display_name="Light sensor",
        protocol_class=ProtocolClass.ANALOG,
        driver_code=LDR_DRIVER,
        pins={"adc": 27},
        unit="raw",
        status=DriverStatus.ACTIVE,
    )


class ConcurrencyProbe:
    """Transport wrapper that records how many execs overlap in flight."""

    def __init__(self, inner: MockBoard) -> None:
        self._inner = inner
        self.port_id = inner.port_id
        self.is_mock = True
        self.active = 0
        self.max_active = 0

    @property
    def connected(self) -> bool:
        return self._inner.connected

    async def connect(self) -> None:
        await self._inner.connect()

    async def exec(self, code: str, timeout_s: float) -> ExecResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            return await self._inner.exec(code, timeout_s)
        finally:
            self.active -= 1

    async def soft_reset(self) -> None:
        await self._inner.soft_reset()

    async def close(self) -> None:
        await self._inner.close()


async def test_exec_serializes_under_the_lock(bus: EventBus, mock_board: MockBoard) -> None:
    mock_board.queue(
        ScriptedExchange(stdout="1\n", delay_s=0.05),
        ScriptedExchange(stdout="2\n", delay_s=0.05),
    )
    probe = ConcurrencyProbe(mock_board)
    session = BoardSession(probe, bus, _fast_settings())
    await session.connect()

    results = await asyncio.gather(
        session.exec("print(1)", timeout_s=1.0),
        session.exec("print(2)", timeout_s=1.0),
    )
    assert probe.max_active == 1  # never two execs on the wire at once
    assert sorted(r.last_line for r in results) == ["1", "2"]


async def test_exec_timeout_triggers_soft_reset_before_release(bus: EventBus, mock_board: MockBoard) -> None:
    mock_board.queue(ScriptedExchange(stdout="never\n", delay_s=1.0))
    session = BoardSession(mock_board, bus, _fast_settings())
    await session.connect()

    result = await session.exec("hang()", timeout_s=0.02)
    assert result.timed_out
    assert mock_board.soft_reset_count == 1  # the next caller inherits a clean line


async def test_exclusive_pauses_and_resumes_poller(bus: EventBus, bus_spy: BusSpy, mock_board: MockBoard) -> None:
    registry = DriverRegistry(bus)
    registry.register(_ldr_record())
    session = BoardSession(mock_board, bus, _fast_settings(), registry=registry)
    await session.connect()

    await session.start_poller()
    await asyncio.sleep(0.05)
    assert len(bus_spy.of_type("sensor.reading")) >= 2  # poller is alive (MockBoard sims answer)
    readings = [e.payload for e in bus_spy.of_type("sensor.reading")]
    assert readings[0]["slug"] == "ldr"
    assert readings[0]["unit"] == "raw"

    async with session.exclusive() as board:
        assert not session.poller_running  # cancelled AND reaped
        bus_spy.drain()
        bus_spy.events.clear()
        await asyncio.sleep(0.05)
        assert bus_spy.of_type("sensor.reading") == []  # paused: silence on the wire

        # the exclusive handle owns the transport directly
        result = await board.exec(LDR_DRIVER + "print(Driver().read())\n")
        assert result.ok

    assert session.poller_running  # restarted on exit
    bus_spy.drain()
    bus_spy.events.clear()
    await asyncio.sleep(0.05)
    assert len(bus_spy.of_type("sensor.reading")) >= 1  # readings flow again

    await session.close()
    assert not session.poller_running


async def test_exclusive_emits_busy_board_status(bus: EventBus, bus_spy: BusSpy, mock_board: MockBoard) -> None:
    session = BoardSession(mock_board, bus, _fast_settings())
    await session.connect()
    bus_spy.drain()
    bus_spy.events.clear()

    async with session.exclusive():
        statuses = [e.payload for e in bus_spy.of_type("board.status")]
        assert statuses[-1]["busy"] is True

    bus_spy.drain()
    statuses = [e.payload for e in bus_spy.events if e.type == "board.status"]
    assert statuses[-1]["busy"] is False


async def test_poller_updates_registry_record(bus: EventBus, mock_board: MockBoard) -> None:
    registry = DriverRegistry(bus)
    registry.register(_ldr_record())
    session = BoardSession(mock_board, bus, _fast_settings(), registry=registry)
    await session.connect()

    await session.start_poller()
    await asyncio.sleep(0.05)
    await session.stop_poller()

    record = registry.get("ldr")
    assert record is not None
    assert record.last_reading is not None
    assert record.last_read_at is not None
