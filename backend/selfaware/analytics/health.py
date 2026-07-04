"""Sensor health scoring and short-horizon degradation trend.

Computed from real accumulated readings only — no synthetic backfill
anywhere in this module. An earlier version of this feature fabricated
years of seasonal history to power a 24h value forecast; that was dropped
because it would sit next to real, honestly-sparse live data and look like
exactly the kind of unverifiable claim this codebase refuses to make
elsewhere. "Not enough data yet" is a legitimate, demoable answer here, not
a gap to hide.

Same discipline as docs/hardware-bringup.md's plausibility checks: a status
or a trend ships with the NAMED reasons behind it, never a bare score. This
is a DIFFERENT check from bringup/plausibility.py's rail-fingerprint gate,
deliberately: that one is a single-sample, ADC-count-specific check
(RAIL_MARGIN out of the fixed 0..65535 u16 range) run once at commissioning
time, for ANALOG class only. This module's railing signal is statistical,
computed against each slug's own OBSERVED historical range, and applies to
any protocol class (including e.g. a digital_bus temperature sensor with no
fixed numeric range at all) — they solve different problems and should stay
separate rather than share a constant that's meaningless outside ADC counts.

Threshold constants (RAIL_EDGE_FRACTION, VARIANCE_RATIO_THRESHOLD,
RISK_DEGRADING/RISK_CRITICAL) are reasonable starting points, NOT
empirically calibrated against real sensor behavior — there isn't real
failure data to calibrate against yet. Revisit once devA's sensors have
produced enough real history to know what a genuine anomaly looks like.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from selfaware.analytics.history import Point

MIN_POINTS_FOR_STATUS = 10  # below this: "unknown", not a guess
MIN_POINTS_FOR_VARIANCE = 20  # below this: the variance signal is skipped, not faked
# The trend compares a "prior" snapshot (all but the last 10 readings) against
# "now" — for the prior snapshot to ever be able to compute a variance signal
# too (not just railing), it needs its own MIN_POINTS_FOR_VARIANCE readings,
# hence the +10 rather than reusing MIN_POINTS_FOR_VARIANCE directly.
MIN_POINTS_FOR_TREND = MIN_POINTS_FOR_VARIANCE + 10

STALE_FACTOR = 5.0  # "no reading in > 5x the effective interval" -> critical
RAIL_EDGE_FRACTION = 0.03  # within 3% of the observed min/max counts as "railed"
RAIL_COUNT_THRESHOLD = 6  # of the last 10 readings
VARIANCE_RATIO_THRESHOLD = 2.5

RISK_DEGRADING = 0.34
RISK_CRITICAL = 0.70
TREND_ETA_CAP_S = 2 * 3600.0  # never project further out than this


@dataclass
class HealthAssessment:
    status: str  # "healthy" | "degrading" | "critical" | "unknown" | "not_monitored"
    reasons: list[str]
    readings_count: int
    baseline_target: int = MIN_POINTS_FOR_STATUS


@dataclass
class TrendAssessment:
    direction: str  # "stable" | "degrading" | "critical" | "insufficient_data"
    eta_s: float | None
    note: str | None


def _sorted_points(points: list[Point]) -> list[Point]:
    """Sort by timestamp only — sorting the full (ts, value) tuple would break
    ties on duplicate timestamps by comparing value, silently reordering
    same-instant readings and corrupting the trend slope calculation."""
    return sorted(points, key=lambda p: p[0])


def _effective_interval_s(ordered: list[Point], fallback_interval_s: float) -> float:
    """The median observed gap between consecutive readings for THIS slug,
    not the raw poller_interval_s config value. A shared poller sweeps every
    active sensor in one cycle under the single lock, so any one slug's real
    cadence is poller_interval_s PLUS the exec time of every other sensor
    polled that cycle — a static config number is systematically wrong for
    any multi-sensor deployment. Falls back to config only when there isn't
    enough history yet to observe a real cadence.
    """
    if len(ordered) < 3:
        return fallback_interval_s
    gaps = [b[0] - a[0] for a, b in zip(ordered, ordered[1:]) if b[0] > a[0]]
    return statistics.median(gaps) if gaps else fallback_interval_s


def _staleness_component(last_ts: float, reference_now: float, expected_interval_s: float) -> tuple[float, str | None]:
    threshold = expected_interval_s * STALE_FACTOR
    if threshold <= 0:
        return 0.0, None  # no meaningful cadence to compare against — don't divide by zero
    stale_s = reference_now - last_ts
    if stale_s <= threshold:
        return 0.0, None
    return min(1.0, stale_s / threshold), f"no reading in {stale_s:.0f}s (expected roughly every {expected_interval_s:.0f}s)"


def _railing_component(values: list[float]) -> tuple[float, str | None]:
    if len(values) < MIN_POINTS_FOR_STATUS:
        return 0.0, None
    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 0:
        return 0.0, None  # zero observed range — a flat signal isn't a railed one
    recent = values[-10:]
    near_edge = sum(1 for v in recent if (v - lo) / span < RAIL_EDGE_FRACTION or (hi - v) / span < RAIL_EDGE_FRACTION)
    if near_edge < RAIL_COUNT_THRESHOLD:
        return 0.0, None
    reason = (
        f"{near_edge} of the last {len(recent)} readings sit at the observed min/max — "
        "a railed-pin fingerprint, not a live signal"
    )
    return near_edge / len(recent), reason


def _variance_component(values: list[float]) -> tuple[float, str | None]:
    if len(values) < MIN_POINTS_FOR_VARIANCE:
        return 0.0, None
    baseline, recent = values[:-10], values[-10:]
    baseline_std = statistics.pstdev(baseline)
    recent_std = statistics.pstdev(recent)
    if baseline_std <= 0:
        if recent_std <= 0:
            return 0.0, None  # both flat — nothing to report
        # baseline was perfectly flat and it isn't anymore — the strongest
        # possible version of this signal, not one to skip for lack of a ratio
        return 1.0, f"recent variance ({recent_std:.2f}) appeared where the historical baseline had none at all"
    ratio = recent_std / baseline_std
    if ratio <= VARIANCE_RATIO_THRESHOLD:
        return 0.0, None
    reason = (
        f"recent variance ({recent_std:.2f}) is over {VARIANCE_RATIO_THRESHOLD:g}x the "
        f"historical baseline ({baseline_std:.2f})"
    )
    return min(1.0, (ratio - 1) / (VARIANCE_RATIO_THRESHOLD - 1)), reason


def _risk_and_reasons(values: list[float]) -> tuple[float, list[str]]:
    """Shared by assess_health's non-staleness component and both of
    assess_trend's snapshots — one place computing "how bad does this value
    series look," so a future third signal or reweighting only needs editing
    once instead of drifting between three copy-pasted call sites."""
    rail_c, rail_reason = _railing_component(values)
    var_c, var_reason = _variance_component(values)
    return max(rail_c, var_c), [r for r in (rail_reason, var_reason) if r]


def _status_from_score(score: float) -> str:
    if score >= RISK_CRITICAL:
        return "critical"
    if score >= RISK_DEGRADING:
        return "degrading"
    return "healthy"


def assess_health(points: list[Point], *, now: float, expected_interval_s: float = 60.0) -> HealthAssessment:
    """The live status: worst-signal-wins across staleness/railing/variance,
    each named in `reasons` — never a bare number."""
    if len(points) < MIN_POINTS_FOR_STATUS:
        return HealthAssessment(
            status="unknown",
            reasons=["not enough history yet to assess health or trend"],
            readings_count=len(points),
        )

    ordered = _sorted_points(points)
    values = [v for _, v in ordered if v == v and abs(v) != float("inf")]  # drop NaN/inf — never let a bad
    # sample from a misbehaving driver silently corrupt min/max/variance math
    if len(values) < MIN_POINTS_FOR_STATUS:
        return HealthAssessment(
            status="unknown",
            reasons=["too many non-finite readings to assess health"],
            readings_count=len(points),
        )

    last_ts = ordered[-1][0]
    interval = _effective_interval_s(ordered, expected_interval_s)
    stale_c, stale_reason = _staleness_component(last_ts, now, interval)
    score, reasons = _risk_and_reasons(values)
    score = max(score, stale_c)
    if stale_reason:
        reasons.insert(0, stale_reason)
    if not reasons:
        reasons = ["readings are within the historical range and arriving on schedule"]

    return HealthAssessment(status=_status_from_score(score), reasons=reasons, readings_count=len(points))


def assess_trend(points: list[Point]) -> TrendAssessment:
    """Compares railing+variance risk as-of 10 readings ago vs. as-of now,
    and extrapolates a capped, short-horizon ETA only while things are
    worsening. Staleness is deliberately excluded here — it's a clock-gap
    signal already surfaced by assess_health's live status, not a trend in
    the value series itself.
    """
    if len(points) < MIN_POINTS_FOR_TREND:
        return TrendAssessment(direction="insufficient_data", eta_s=None, note=None)

    ordered = _sorted_points(points)
    values = [v for _, v in ordered if v == v and abs(v) != float("inf")]
    if len(values) < MIN_POINTS_FOR_TREND:
        return TrendAssessment(direction="insufficient_data", eta_s=None, note=None)

    prior_slice = ordered[:-10]
    prior_values = values[:-10]
    risk_prior, _ = _risk_and_reasons(prior_values)
    risk_now, _ = _risk_and_reasons(values)

    t_prior = prior_slice[-1][0]  # always non-empty: len(ordered) >= MIN_POINTS_FOR_TREND > 10
    t_now = ordered[-1][0]
    dt = t_now - t_prior

    if risk_now >= RISK_CRITICAL:
        return TrendAssessment(direction="critical", eta_s=0.0, note="already critical — no ETA needed")

    if dt <= 0 or risk_now <= 0:
        return TrendAssessment(direction="stable", eta_s=None, note=None)

    slope = (risk_now - risk_prior) / dt  # risk units per second
    if slope <= 0:
        return TrendAssessment(direction="stable", eta_s=None, note=None)

    eta_s = (RISK_CRITICAL - risk_now) / slope
    if eta_s > TREND_ETA_CAP_S:
        return TrendAssessment(
            direction="stable",
            eta_s=None,
            note="degrading slowly — not expected to reach critical within the next 2 hours at this rate",
        )

    return TrendAssessment(
        direction="degrading",
        eta_s=eta_s,
        note=f"degrading — projected to cross into critical in ~{eta_s / 60.0:.0f} min",
    )
