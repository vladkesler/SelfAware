"""AppState — the one bag of live services, hung on app.state.selfaware.

Built exactly once by the lifespan (app.py), read by ws/rest/handlers.
Handlers get the whole bag deliberately: on a one-day build, plumbing six
narrow interfaces through closures buys nothing over one typed dataclass.

chat_histories is keyed by connection id via CURRENT_CONNECTION (a
contextvar): the ws receive loop sets it once per socket, and because
CommandRouter runs handlers via asyncio.create_task — which COPIES the
current context — the cmd.chat handler task inherits the right id for free.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from selfaware.analytics.history import HistoryStore
from selfaware.bringup.loop import AuthorFn, CommissionRunner
from selfaware.bringup.service import CommissionService
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.commands import CommandRouter
from selfaware.hardware.base import BoardTransport
from selfaware.hardware.session import BoardSession
from selfaware.registry.store import DriverRegistry

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage

    from selfaware.agents.deps import CopilotDeps
    from selfaware.memory.client import MemoryClient

# Set by ws.py per connection; "rest" is the default for non-WS callers.
CURRENT_CONNECTION: ContextVar[str] = ContextVar("selfaware_connection", default="rest")


@dataclass
class AppState:
    settings: Settings
    bus: EventBus
    router: CommandRouter
    transport: BoardTransport
    session: BoardSession
    registry: DriverRegistry
    history: HistoryStore
    memory: "MemoryClient"
    runner: CommissionRunner
    commissioner: CommissionService
    copilot_deps: "CopilotDeps"
    author: AuthorFn
    # per-connection copilot conversations: connection id -> ModelMessage list
    chat_histories: dict[str, "list[ModelMessage]"] = field(default_factory=dict)
    # anything build-day needs to stash without another schema change
    extras: dict[str, Any] = field(default_factory=dict)
