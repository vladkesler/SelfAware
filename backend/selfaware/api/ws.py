"""THE /ws endpoint — one socket carries everything (docs/event-protocol.md).

Frame lifecycle per connection:
  1. accept, subscribe to the bus FIRST (no gap between hello and the stream)
  2. send system.hello with seq=0 — built here, not via the bus, because hello
     is per-connection state (a bus publish would spam every other client).
     seq=0 sits below every bus seq, so client-side monotonicity holds; on
     reconnect the client rehydrates from hello and never replays.
  3. sender task: async for event in subscription -> send JSON
  4. receiver loop (this coroutine): parse Command -> router.dispatch;
     a malformed frame gets system.error and the socket STAYS ALIVE.
  5. finally: cancel sender, unsubscribe, drop this connection's chat history.
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

import selfaware
from selfaware.api.state import CURRENT_CONNECTION, AppState
from selfaware.events.bus import Subscription
from selfaware.events.envelope import Command, Event
from selfaware.events.payloads import ErrorPayload, HelloPayload
from selfaware.events.types import EventType

router = APIRouter()


def _hello_event(state: AppState) -> Event:
    """Full-state snapshot; the ONE envelope not stamped by the bus (seq=0)."""
    payload = HelloPayload(
        server_version=selfaware.__version__,
        protocol_v=selfaware.PROTOCOL_VERSION,
        model=state.settings.model,
        board=state.session.board_status(),
        drivers=state.registry.summaries(),
    )
    return Event(
        type=EventType.SYSTEM_HELLO,
        ts=datetime.now(UTC),
        seq=0,
        payload=payload.model_dump(mode="json"),
    )


async def _send_loop(websocket: WebSocket, sub: Subscription) -> None:
    async for event in sub:
        await websocket.send_text(event.model_dump_json())


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    state: AppState = websocket.app.state.selfaware
    await websocket.accept()

    conn_id = uuid4().hex
    CURRENT_CONNECTION.set(conn_id)  # inherited by every handler task this socket spawns

    sub = state.bus.subscribe()
    sender: asyncio.Task[None] | None = None
    try:
        await websocket.send_text(_hello_event(state).model_dump_json())
        # Rehydrate discovery presences: the watcher's device_found events fired
        # before this socket existed, and steady-state scans diff to silence, so
        # a fresh client would otherwise never learn about already-present
        # devices. Replay current presences here (same rehydrate-on-connect
        # contract as hello), on THIS socket only — before the sender task starts
        # so two coroutines never write the socket concurrently.
        watcher = state.extras.get("watcher")
        if watcher is not None:
            now = datetime.now(UTC)
            for presence in watcher.current_presences():
                event = Event(
                    type=EventType.DISCOVERY_DEVICE_FOUND,
                    ts=now,
                    seq=0,
                    payload=presence.model_dump(mode="json"),
                )
                await websocket.send_text(event.model_dump_json())
        sender = asyncio.create_task(_send_loop(websocket, sub), name=f"ws-send-{conn_id[:8]}")

        while True:
            raw = await websocket.receive_text()
            try:
                cmd = Command.model_validate_json(raw)
            except ValidationError as exc:
                # Bad frame != dead socket: name the sin, keep listening.
                state.bus.publish(
                    EventType.SYSTEM_ERROR,
                    ErrorPayload(
                        code="malformed_command",
                        message="frame is not a valid Command envelope",
                        detail=str(exc.errors()[0].get("msg", "invalid")) if exc.errors() else None,
                    ),
                )
                continue
            await state.router.dispatch(cmd)
    except WebSocketDisconnect:
        pass
    finally:
        if sender is not None:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender
        state.bus.unsubscribe(sub)
        state.chat_histories.pop(conn_id, None)
