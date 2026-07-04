"""EventBus contract: envelope stamping, fan-out, drop-oldest, seq monotonicity."""

import asyncio

from selfaware.events.bus import EventBus
from selfaware.events.payloads import AgentThoughtPayload
from selfaware.events.types import EventType


def _thought(text: str) -> AgentThoughtPayload:
    return AgentThoughtPayload(agent="copilot", text=text)


def test_publish_stamps_envelope(bus: EventBus) -> None:
    event = bus.publish(EventType.AGENT_THOUGHT, _thought("hello"))
    assert event.v == 1
    assert event.type == "agent.thought"
    assert event.seq == 1
    assert event.ts.tzinfo is not None  # UTC-aware
    assert event.payload == {"agent": "copilot", "text": "hello"}


def test_seq_is_global_and_monotonic(bus: EventBus) -> None:
    seqs = [bus.publish(EventType.AGENT_THOUGHT, _thought(str(i))).seq for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


async def test_fan_out_to_all_subscribers(bus: EventBus) -> None:
    a, b = bus.subscribe(), bus.subscribe()
    bus.publish(EventType.AGENT_THOUGHT, _thought("x"))
    got_a = await asyncio.wait_for(anext(aiter(a)), timeout=1)
    got_b = await asyncio.wait_for(anext(aiter(b)), timeout=1)
    assert got_a.seq == got_b.seq == 1


async def test_unsubscribed_receives_nothing(bus: EventBus) -> None:
    sub = bus.subscribe()
    bus.unsubscribe(sub)
    bus.publish(EventType.AGENT_THOUGHT, _thought("x"))
    assert bus.subscriber_count == 0
    with __import__("pytest").raises(asyncio.TimeoutError):
        await asyncio.wait_for(anext(aiter(sub)), timeout=0.05)


async def test_slow_subscriber_drops_oldest_not_publisher(bus_factory=None) -> None:
    bus = EventBus(queue_size=3)
    sub = bus.subscribe()
    for i in range(5):  # 5 events into a queue of 3 -> events 1,2 dropped
        bus.publish(EventType.AGENT_THOUGHT, _thought(str(i)))
    received = [await asyncio.wait_for(anext(aiter(sub)), timeout=1) for _ in range(3)]
    assert [e.seq for e in received] == [3, 4, 5]  # oldest sacrificed, order kept
