"""Command routing: cmd.type string -> async handler, crash-proof.

Handlers are registered in api/handlers.py, bound to AppState via closures.
Dispatch contract (what the frontend relies on):
  1. Unknown type        -> system.error{code: "unknown_command", cmd_id}
  2. Known type          -> system.ack{cmd_id}, then the handler runs AS A TASK
                            (a 60s commission must never block the WS receive loop)
  3. Handler raises      -> system.error{cmd_id, code: "handler_error"};
                            the socket stays alive, always.
"""

import asyncio
from collections.abc import Awaitable, Callable

from selfaware.events.bus import EventBus
from selfaware.events.envelope import Command
from selfaware.events.payloads import AckPayload, ErrorPayload
from selfaware.events.types import EventType

CommandHandler = Callable[[Command], Awaitable[None]]


class CommandRouter:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._handlers: dict[str, CommandHandler] = {}
        self._tasks: set[asyncio.Task[None]] = set()  # keep refs so tasks aren't GC'd

    def register(self, cmd_type: str, handler: CommandHandler) -> None:
        self._handlers[str(cmd_type)] = handler

    async def dispatch(self, cmd: Command) -> None:
        handler = self._handlers.get(cmd.type)
        if handler is None:
            self._bus.publish(
                EventType.SYSTEM_ERROR,
                ErrorPayload(code="unknown_command", message=f"unknown command type: {cmd.type}", cmd_id=cmd.id),
            )
            return

        self._bus.publish(EventType.SYSTEM_ACK, AckPayload(cmd_id=cmd.id))
        task = asyncio.create_task(self._run(handler, cmd))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, handler: CommandHandler, cmd: Command) -> None:
        try:
            await handler(cmd)
        except Exception as exc:  # noqa: BLE001 — commands never crash the socket
            self._bus.publish(
                EventType.SYSTEM_ERROR,
                ErrorPayload(code="handler_error", message=str(exc), cmd_id=cmd.id, detail=type(exc).__name__),
            )
