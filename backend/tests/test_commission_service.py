"""CommissionService's outcome store — the poll-shaped truth behind
GET /api/commission/{id}.

The property under test: every way a commission can end (passed, failed,
CRASHED) leaves a queryable terminal outcome, because the REST/MCP callers
poll rather than await — a caller who timed out and lost its HTTP request
must still be able to learn what happened.
"""

import asyncio
from typing import Any

import pytest

from selfaware.bringup.models import (
    AttemptRecord,
    BringupSpec,
    CommissionResult,
    CommissionStage,
    CommissionStatus,
    ProtocolClass,
)
from selfaware.bringup.service import _OUTCOME_RING_CAP, CommissionService
from selfaware.events.bus import EventBus
from selfaware.events.types import EventType

SPEC = BringupSpec(
    slug="ldr",
    display_name="Light sensor",
    protocol_class=ProtocolClass.ANALOG,
    pins={"adc": 27},
    unit="%",
)


class StubRunner:
    """Stands in for CommissionRunner: returns a canned result or raises."""

    def __init__(self, result: CommissionResult | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    async def run(self, spec: BringupSpec, commission_id: str) -> CommissionResult:
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


async def _drain(service: CommissionService) -> None:
    """Wait for the background task AND its done-callback to run."""
    assert service._current is not None
    await asyncio.gather(service._current, return_exceptions=True)
    await asyncio.sleep(0)  # done-callbacks run on the next loop tick


def _failed_result() -> CommissionResult:
    return CommissionResult(
        spec=SPEC,
        status=CommissionStatus.FAILED,
        attempts=[
            AttemptRecord(attempt=1, stage_reached=CommissionStage.TEST, traceback="OSError: boom", passed=False),
        ],
        failure_reason="budget exhausted",
    )


async def test_crash_is_a_queryable_outcome_and_still_loud() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    service = CommissionService(StubRunner(exc=RuntimeError("wire fell out")), bus)  # type: ignore[arg-type]
    cid = service.enqueue(SPEC)
    assert cid is not None
    await _drain(service)

    outcome = service.status(cid)
    assert outcome is not None
    assert outcome["status"] == "crashed"
    assert "wire fell out" in outcome["failure_reason"]
    assert outcome["error_type"] == "RuntimeError"

    event = sub._queue.get_nowait()  # the crash must still hit the bus
    assert event.type == EventType.SYSTEM_ERROR
    assert event.payload["code"] == "commission_crash"


async def test_failed_result_carries_reason_and_attempts() -> None:
    service = CommissionService(StubRunner(result=_failed_result()), EventBus())  # type: ignore[arg-type]
    cid = service.enqueue(SPEC)
    assert cid is not None
    await _drain(service)

    outcome = service.status(cid)
    assert outcome is not None
    assert outcome["status"] == "failed"
    assert outcome["failure_reason"] == "budget exhausted"
    assert outcome["attempts_used"] == 1
    assert outcome["attempts"][0]["traceback"] == "OSError: boom"
    assert outcome["tool"] is None  # nothing armed — no tool to advertise


async def test_passed_result_advertises_the_tool() -> None:
    result = CommissionResult(
        spec=SPEC,
        status=CommissionStatus.PASSED,
        attempts=[AttemptRecord(attempt=1, stage_reached=CommissionStage.TEST, reading=42.0, passed=True)],
        final_reading=42.0,
    )
    service = CommissionService(StubRunner(result=result), EventBus())  # type: ignore[arg-type]
    cid = service.enqueue(SPEC)
    assert cid is not None
    await _drain(service)

    outcome = service.status(cid)
    assert outcome is not None
    assert outcome["status"] == "passed"
    assert outcome["tool"] == "read_ldr"
    assert outcome["final_reading"] == 42.0


async def test_running_status_for_the_inflight_id() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowRunner:
        async def run(self, spec: BringupSpec, commission_id: str) -> CommissionResult:
            started.set()
            await release.wait()
            return _failed_result()

    service = CommissionService(SlowRunner(), EventBus())  # type: ignore[arg-type]
    cid = service.enqueue(SPEC)
    assert cid is not None
    await started.wait()
    status: dict[str, Any] | None = service.status(cid)
    assert status is not None and status["status"] == "running"
    release.set()
    await _drain(service)
    final = service.status(cid)
    assert final is not None and final["status"] == "failed"


async def test_outcome_ring_caps() -> None:
    service = CommissionService(StubRunner(result=_failed_result()), EventBus())  # type: ignore[arg-type]
    ids = []
    for _ in range(_OUTCOME_RING_CAP + 4):
        cid = service.enqueue(SPEC)
        assert cid is not None
        await _drain(service)
        ids.append(cid)
    assert len(service._outcomes) == _OUTCOME_RING_CAP
    assert service.status(ids[0]) is None  # oldest evicted
    assert service.status(ids[-1]) is not None


def test_unknown_id_is_none() -> None:
    service = CommissionService(StubRunner(result=_failed_result()), EventBus())  # type: ignore[arg-type]
    assert service.status("nope") is None
