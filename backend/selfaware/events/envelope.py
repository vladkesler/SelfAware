"""Wire envelopes — the outermost shape of every frame on the WebSocket.

Server -> client: Event   {v, type, ts, seq, payload}
Client -> server: Command {type, id, payload}

seq semantics (documented in docs/event-protocol.md and relied on by the UI):
  * seq is GLOBAL per backend process and strictly monotonic — stamped by the
    EventBus, the only writer.
  * Gaps are LEGAL: a slow subscriber's queue drops oldest events rather than
    backpressuring the commission loop.
  * Reconnect = rehydrate: system.hello restates full state (board + drivers),
    so a client never needs to replay missed events.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class Event(BaseModel):
    """Server -> client envelope. Built exclusively by EventBus.publish()."""

    v: Literal[1] = 1
    type: str  # canonical value from EventType; str here so unknown types survive round-trips
    ts: datetime  # UTC, ISO-8601 on the wire
    seq: int  # global, monotonic, gaps legal
    payload: dict[str, Any]  # model_dump() of the matching payloads.py model


class Command(BaseModel):
    """Client -> server envelope.

    Every dispatched command is answered: system.ack{cmd_id} on acceptance,
    system.error{cmd_id, ...} on rejection or handler crash — the socket
    itself never dies from a bad command.
    """

    type: str  # canonical value from CommandType
    id: UUID  # client-generated correlation id
    payload: dict[str, Any]
