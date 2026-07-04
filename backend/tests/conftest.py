"""Shared fixtures. Extended in PR3 with fake_registry / noop_memory /
TestModel agent fixtures.

Global rule: the suite must be green with no .env, no docker, no USB device,
and no API key. PR3 adds `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False`
here so any accidental real provider call fails loudly. Settings are always
constructed with `_env_file=None` so a developer's .env can never leak in.
"""

import asyncio

import pytest

from selfaware.config import Settings
from selfaware.events.bus import EventBus, Subscription
from selfaware.events.envelope import Event
from selfaware.hardware.mock_board import MockBoard


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def settings() -> Settings:
    """Env-isolated settings; mock_board=True is the suite's only board."""
    return Settings(_env_file=None, mock_board=True)


@pytest.fixture
def mock_board() -> MockBoard:
    return MockBoard()


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
