"""Shared fixtures. Extended in PR3 with bus_spy / mock_board / fake_registry /
noop_memory / TestModel agent fixtures.

Global rule: the suite must be green with no .env, no docker, no USB device,
and no API key. PR3 adds `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False`
here so any accidental real provider call fails loudly.
"""

import pytest

from selfaware.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()
