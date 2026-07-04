"""analytics/health.py — the four real states, and the REST endpoints that
expose them. No synthetic seasonal data anywhere: every series here is
built by hand to exercise one named signal at a time.
"""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from selfaware.analytics.health import assess_health, assess_trend
from selfaware.analytics.history import HistoryStore
from selfaware.api.app import create_app
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.payloads import DriverRegisteredPayload, DriverUpdatedPayload, SensorReadingPayload
from selfaware.events.types import EventType, ProtocolClass

TOKEN = "test-secret"


def _settings(**overrides) -> Settings:
    overrides.setdefault("poller_interval_s", 60.0)
    return Settings(_env_file=None, mock_board=True, mock_author=True, **overrides)


def _flat_series(n: int, value: float = 22.0, start_ts: float = 0.0, interval_s: float = 60.0) -> list[tuple[float, float]]:
    return [(start_ts + i * interval_s, value) for i in range(n)]


def test_unknown_below_ten_points() -> None:
    health = assess_health(_flat_series(4), now=4 * 60.0)
    assert health.status == "unknown"
    assert health.readings_count == 4


def test_healthy_flat_series() -> None:
    points = _flat_series(30)
    health = assess_health(points, now=points[-1][0], expected_interval_s=60.0)
    assert health.status == "healthy"
    trend = assess_trend(points)
    assert trend.direction == "stable"


def test_stale_reading_is_critical() -> None:
    points = _flat_series(30)
    # "now" is way past the last reading, relative to a 60s expected interval
    now = points[-1][0] + 60.0 * 10
    health = assess_health(points, now=now, expected_interval_s=60.0)
    assert health.status == "critical"
    assert "no reading in" in health.reasons[0]


def test_railed_readings_are_critical() -> None:
    # 20 points at 22.0, then 8 of the last 10 pinned at the max (100.0) —
    # a classic railed-pin fingerprint, not a live signal.
    points = _flat_series(20, value=22.0)
    railed_start = points[-1][0] + 60.0
    for i in range(8):
        points.append((railed_start + i * 60.0, 100.0))
    points.append((railed_start + 8 * 60.0, 22.5))
    points.append((railed_start + 9 * 60.0, 21.5))
    health = assess_health(points, now=points[-1][0], expected_interval_s=60.0)
    assert health.status == "critical"
    assert any("railed-pin fingerprint" in r for r in health.reasons)


def test_rising_variance_degrades_and_projects_an_eta() -> None:
    # 20 stable points (std ~0), then a recent window with real spread —
    # enough to push recent variance well past the 2.5x baseline threshold.
    points = _flat_series(20, value=22.0)
    last_ts = points[-1][0]
    noisy = [22.0, 24.0, 20.0, 25.0, 19.0, 26.0, 18.0, 27.0, 17.0, 28.0]
    for i, v in enumerate(noisy):
        points.append((last_ts + (i + 1) * 60.0, v))

    health = assess_health(points, now=points[-1][0], expected_interval_s=60.0)
    assert health.status in ("degrading", "critical")
    assert any("variance" in r for r in health.reasons)

    trend = assess_trend(points)
    assert trend.direction in ("degrading", "critical")


def test_trend_insufficient_data_below_thirty_points() -> None:
    # MIN_POINTS_FOR_TREND = MIN_POINTS_FOR_VARIANCE(20) + 10 = 30, so the
    # "prior" snapshot (all but the last 10) can also compute a variance
    # signal, not just railing.
    trend = assess_trend(_flat_series(25))
    assert trend.direction == "insufficient_data"
    assert trend.eta_s is None


def test_effective_interval_self_calibrates_past_a_slow_multi_sensor_poll_cycle() -> None:
    """A slug polled every 5s in practice (e.g. several sensors sharing one
    poller cycle) must not be flagged stale against a stale config value of
    poller_interval_s=1.0 — the real observed cadence should be used instead."""
    points = _flat_series(15, interval_s=5.0)
    now = points[-1][0] + 6.0  # one real interval late, not 6x a wrong 1.0s assumption
    health = assess_health(points, now=now, expected_interval_s=1.0)
    assert health.status == "healthy"


def test_nonfinite_readings_are_dropped_not_corrupting_the_score() -> None:
    points = _flat_series(15, value=22.0)
    points.append((points[-1][0] + 60.0, float("nan")))
    points.append((points[-1][0] + 120.0, float("inf")))
    health = assess_health(points, now=points[-1][0] + 120.0, expected_interval_s=60.0)
    assert health.status == "healthy"


def _commission_ldr(ws) -> None:
    assert ws.receive_json()["type"] == "system.hello"
    ws.send_json({"type": "cmd.commission", "id": str(uuid4()), "payload": {"preset_slug": "ldr"}})
    for _ in range(300):
        frame = ws.receive_json()
        if frame["type"] == "commission.passed":
            return
    raise AssertionError("commission never passed")


def test_health_endpoint_reports_unknown_for_a_freshly_commissioned_driver() -> None:
    """Right after commissioning there's at most one real reading — the
    endpoint must say 'unknown', never guess a status from almost nothing."""
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        resp = client.get("/api/drivers/ldr/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unknown"
        assert body["trend"]["direction"] == "insufficient_data"
        assert body["baseline_target"] == 10


def test_health_endpoint_unknown_slug_is_404() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        resp = client.get("/api/drivers/no_such_slug/health")
        assert resp.status_code == 404


def test_health_endpoint_reports_not_monitored_for_an_actuator() -> None:
    """An OUTPUT-class driver never publishes sensor.reading, so it must not
    sit at 'unknown' forever implying data is still coming — 'not_monitored'
    says plainly this feature doesn't apply to actuators."""
    app = create_app(_settings())
    with TestClient(app) as client:
        state = app.state.selfaware
        from selfaware.registry.models import DriverRecord, DriverStatus

        state.registry.register(
            DriverRecord(
                slug="relay",
                display_name="Relay",
                protocol_class=ProtocolClass.OUTPUT,
                driver_code="class Driver:\n    def set(self, level):\n        pass\n",
                pins={"pwm": 12},
                status=DriverStatus.ACTIVE,
            )
        )
        resp = client.get("/api/drivers/relay/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_monitored"


async def _drain(store: HistoryStore, task: asyncio.Task) -> None:
    """Give the background run() loop a few event-loop turns to process
    whatever was just published, without a fixed sleep."""
    for _ in range(20):
        await asyncio.sleep(0)
    assert not task.done() or task.cancelled(), "history.run() must not have died"


async def test_bad_event_does_not_kill_the_history_listener() -> None:
    bus = EventBus()
    store = HistoryStore(bus)
    task = asyncio.create_task(store.run())
    await asyncio.sleep(0)  # let run() reach its subscribe() call

    # a malformed payload for a type this store understands
    bus.publish(EventType.SENSOR_READING, DriverRegisteredPayload(
        slug="x", display_name="x", protocol_class=ProtocolClass.ANALOG, pins={}, tool_names=[], code_hash="x",
    ))  # wrong payload shape for SENSOR_READING — must not crash the listener

    bus.publish(EventType.SENSOR_READING, SensorReadingPayload(slug="ldr", value=41250.0))
    await _drain(store, task)
    assert store.series("ldr") == [] or store.series("ldr")[-1][1] == 41250.0

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_history_cleared_on_driver_registered() -> None:
    """A slug's very first commission — DRIVER_REGISTERED."""
    bus = EventBus()
    store = HistoryStore(bus)
    task = asyncio.create_task(store.run())
    await asyncio.sleep(0)

    bus.publish(EventType.SENSOR_READING, SensorReadingPayload(slug="ldr", value=100.0))
    await _drain(store, task)
    assert store.series("ldr")

    bus.publish(
        EventType.DRIVER_REGISTERED,
        DriverRegisteredPayload(
            slug="ldr", display_name="LDR", protocol_class=ProtocolClass.ANALOG,
            pins={"adc": 27}, tool_names=["read_ldr"], code_hash="abc123",
        ),
    )
    await _drain(store, task)
    assert store.series("ldr") == []

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_history_cleared_on_recommission_but_not_on_repair() -> None:
    """bringup/loop.py::_admit() only calls register() (-> DRIVER_REGISTERED)
    for a slug's first-ever commission; every later commission of an
    EXISTING slug goes through update_code(reason="recommission")
    (-> DRIVER_UPDATED) instead — confirmed against the real running server,
    not just a hand-built event. That's the path that actually needs to
    clear history; reason="repair" must NOT."""
    bus = EventBus()
    store = HistoryStore(bus)
    task = asyncio.create_task(store.run())
    await asyncio.sleep(0)

    bus.publish(EventType.SENSOR_READING, SensorReadingPayload(slug="ldr", value=100.0))
    await _drain(store, task)
    assert store.series("ldr")

    bus.publish(EventType.DRIVER_UPDATED, DriverUpdatedPayload(slug="ldr", code_hash="def456", reason="repair"))
    await _drain(store, task)
    assert store.series("ldr")  # repair: same physical sensor, history stays

    bus.publish(EventType.DRIVER_UPDATED, DriverUpdatedPayload(slug="ldr", code_hash="ghi789", reason="recommission"))
    await _drain(store, task)
    assert store.series("ldr") == []  # recommission: possibly a different device, clear

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_history_endpoint_reflects_seeded_points() -> None:
    app = create_app(_settings())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        _commission_ldr(ws)
        state = app.state.selfaware
        state.history.seed("ldr", _flat_series(5, value=41250.0))
        resp = client.get("/api/drivers/ldr/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "ldr"
        assert len(body["points"]) >= 5
