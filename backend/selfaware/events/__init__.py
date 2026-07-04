"""The typed language of the system.

Everything the frontend renders and every command it sends flows through
the models in this package. `docs/event-protocol.md` is the canonical
human-readable contract; `payloads.py` is its executable twin. The two are
kept in lockstep by hand (deliberate: no codegen toolchain on a 1-day build)
— if you change one, change both, plus `frontend/src/types/events.ts`.
"""

from selfaware.events.envelope import Command, Event
from selfaware.events.types import CommandType, EventType

__all__ = ["Command", "CommandType", "Event", "EventType"]
