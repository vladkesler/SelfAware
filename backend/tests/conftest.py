"""Shared fixtures.

Global rule: the suite must be green with no .env, no docker, no USB device,
and no API key. `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False` (module
level, below) makes any accidental real provider call fail loudly —
TestModel/FunctionModel are the only models that run here. Settings are
always constructed with `_env_file=None` so a developer's .env can never
leak into the suite.
"""

import asyncio
import os

import pytest
from pydantic_ai import models

from selfaware.config import Settings
from selfaware.events.bus import EventBus, Subscription
from selfaware.events.envelope import Event
from selfaware.hardware.mock_board import MockBoard
from selfaware.memory.client import NullMemoryClient
from selfaware.registry.store import DriverRegistry

models.ALLOW_MODEL_REQUESTS = False  # any real provider call RAISES, suite-wide


@pytest.fixture(autouse=True)
def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`make test` exports the root .env into the process environment;
    Settings(_env_file=None) skips the file but still reads os.environ.
    Strip every SELFAWARE_* switch and provider key so a developer's .env
    can never steer the suite (mock flags, models, keys)."""
    for key in list(os.environ):
        if key.startswith("SELFAWARE_") or key.endswith("_API_KEY"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def settings() -> Settings:
    """Env-isolated settings; mock_board=True is the suite's only board.

    mock_pace_s=0: the theatrical demo pacing must NEVER slow the suite."""
    return Settings(_env_file=None, mock_board=True, mock_pace_s=0.0)


@pytest.fixture
def mock_board() -> MockBoard:
    return MockBoard()


@pytest.fixture
def fake_registry(bus: EventBus) -> DriverRegistry:
    """A real DriverRegistry on the test bus — 'fake' only in that tests may
    register records directly, bypassing the loop's admission gate."""
    return DriverRegistry(bus)


@pytest.fixture
def noop_memory() -> NullMemoryClient:
    return NullMemoryClient()


class BusSpy:
    """Subscription-draining helper: assert on published events without racing.

    publish() is sync and puts events on the subscription queue immediately,
    so drain() right after the code under test sees everything, in order.
    """

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.sub: Subscription = bus.subscribe()
        self.events: list[Event] = []  # everything drained so far, cumulative

    def drain(self) -> list[Event]:
        """Pull all currently queued events (non-blocking); returns the new batch."""
        batch: list[Event] = []
        while True:
            try:
                batch.append(self.sub._queue.get_nowait())  # noqa: SLF001 — test-only peek
            except asyncio.QueueEmpty:
                break
        self.events.extend(batch)
        return batch

    def types(self) -> list[str]:
        """Types of the NEXT drained batch (convenience for order assertions)."""
        return [e.type for e in self.drain()]

    def of_type(self, event_type: str) -> list[Event]:
        """Drain, then filter the cumulative record by type."""
        self.drain()
        return [e for e in self.events if e.type == event_type]


@pytest.fixture
def bus_spy(bus: EventBus) -> BusSpy:
    return BusSpy(bus)
