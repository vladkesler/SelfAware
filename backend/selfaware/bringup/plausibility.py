"""Per-protocol-class plausibility verdicts — HOST-DEFINED, never the model's opinion.

The honesty floor, in code: plausible-in-range is necessary but NOT liveness.
A floating pin sits noisily mid-scale and a railed pin looks like a reading —
both would pass a naive range check on a sensor that isn't even wired. So the
predicates below encode the wiring fingerprints too, and the two-sample
liveness check (value MOVES with stimulus) is a named build-day stub, not a
forgotten TODO.
"""

from pydantic import BaseModel

from selfaware.bringup.models import BringupSpec, ProtocolClass

# ADC rail fingerprint margin (u16 counts). A healthy analog source idles away
# from the rails; a flat value within this margin of 0/65535 is the classic
# "right module, wrong pin" signature (digital/ground-ish pin of the module).
RAIL_MARGIN = 600
U16_MAX = 65535

# Cross-modal gate margins: the quietest driven sample must clear the loudest
# ambient one by BOTH a ratio AND an absolute raw margin — scale-invariant, so
# whatever units the model picked cannot game the gate.
CROSS_MODAL_RATIO = 1.5
CROSS_MODAL_ABS_MARGIN = 1000.0


class Verdict(BaseModel):
    passed: bool
    reason: str | None = None  # e.g. 'value 65535 railed high: wrong-pin signature'
    value: float | None = None


def check(spec: BringupSpec, raw_last_line: str) -> Verdict:
    """Parse the harness's last stdout line and dispatch per protocol class."""
    try:
        value = float(raw_last_line)
    except (TypeError, ValueError):
        return Verdict(passed=False, reason=f"unparseable reading: {raw_last_line!r}")

    match spec.protocol_class:
        case ProtocolClass.ANALOG:
            return analog_plausible(value, spec)
        case ProtocolClass.DIGITAL_BUS:
            return bus_plausible(value, spec)
        case ProtocolClass.PULSE_TIMING:
            return pulse_plausible(value, spec)
        case ProtocolClass.OUTPUT:
            # Soft-verify tier: the payload ran set()/set(0) without a
            # traceback and printed its sentinel. The REAL output gate is
            # output_cross_modal(), wired in when verify_with_slug is set.
            return Verdict(passed=True, value=value, reason="output soft-verify: loaded and ran, no traceback")
    return Verdict(passed=False, reason=f"unknown protocol class: {spec.protocol_class}")  # pragma: no cover


def _range_check(value: float, spec: BringupSpec) -> Verdict | None:
    """Shared expected_min/expected_max window; None means in-window."""
    if spec.expected_min is not None and value < spec.expected_min:
        return Verdict(passed=False, value=value, reason=f"value {value:g} below expected_min {spec.expected_min:g}")
    if spec.expected_max is not None and value > spec.expected_max:
        return Verdict(passed=False, value=value, reason=f"value {value:g} above expected_max {spec.expected_max:g}")
    return None


def analog_plausible(value: float, spec: BringupSpec) -> Verdict:
    """In-window AND not parked on a rail.

    Rail check runs even when the spec window spans the full u16 range —
    that is the whole point: 0..65535 'in range' would otherwise bless the
    wrong-pin signature.
    """
    if value <= RAIL_MARGIN:
        return Verdict(passed=False, value=value, reason=f"value {value:g} railed low (~0): wrong-pin/ground signature")
    if value >= U16_MAX - RAIL_MARGIN:
        return Verdict(
            passed=False, value=value, reason=f"value {value:g} railed high (~65535): wrong-pin/digital signature"
        )
    return _range_check(value, spec) or Verdict(passed=True, value=value)


def bus_plausible(value: float, spec: BringupSpec) -> Verdict:
    """Range check only — bus health is judged upstream from the traceback.

    Errno classification (ETIMEDOUT-class = timeout/clock-stretch vs
    EIO/ENODEV-class = NAK/missing device) is a build-day repair-prompt
    concern; the values are port-specific, so never match literal ints here.
    """
    return _range_check(value, spec) or Verdict(passed=True, value=value)


def pulse_plausible(value: float, spec: BringupSpec) -> Verdict:
    """time_pulse_us returns a NEGATIVE SENTINEL on timeout — it does not raise.

    Negative/zero is 'no echo': non-fatal, not a distance, and NOT a pass —
    the repair prompt gets it as an honest reason.
    """
    if value <= 0:
        return Verdict(
            passed=False,
            value=value,
            reason=f"no echo: time_pulse_us returned {value:g} (negative sentinel = timeout, not a distance)",
        )
    return _range_check(value, spec) or Verdict(passed=True, value=value)


def output_cross_modal(
    ambient: list[float],
    driven: list[float],
    ratio: float = CROSS_MODAL_RATIO,
    abs_margin: float = CROSS_MODAL_ABS_MARGIN,
) -> Verdict:
    """The action-half gate: reality must move, scale-invariantly.

    min(driven) must clear max(ambient) by BOTH a ratio and an absolute raw
    margin — robust to the model's unit choice and to room noise. A failure
    here is the physics-flavored repair signal: 'you drove it but nothing
    moved' (the passive-buzzer-on-DC beat).
    """
    if not ambient or not driven:
        return Verdict(passed=False, reason="cross-modal verify needs ambient and driven samples")
    loudest_ambient = max(ambient)
    quietest_driven = min(driven)
    ratio_ok = quietest_driven >= loudest_ambient * ratio
    margin_ok = (quietest_driven - loudest_ambient) >= abs_margin
    if ratio_ok and margin_ok:
        return Verdict(passed=True, value=quietest_driven)
    return Verdict(
        passed=False,
        value=quietest_driven,
        reason=(
            f"you drove it but nothing moved: quietest driven {quietest_driven:g} vs "
            f"loudest ambient {loudest_ambient:g} (need >= {ratio:g}x AND +{abs_margin:g})"
        ),
    )


def liveness_delta(before: float, after: float, spec: BringupSpec) -> Verdict:
    """Two-sample movement check under stimulus — real liveness, not range.

    Build-day job: wire into the TEST stage as an optional second sample —
    prompt the human with spec.stimulus_hint ('cover the sensor'), re-read,
    and require |after - before| to clear a per-class delta. Offline, the
    MockBoard's stimulate(slug, delta) drives this beat.
    """
    raise NotImplementedError("build day: per-class movement threshold under stimulus_hint")
