"""Host plausibility verdicts: rail fingerprints, pulse sentinels, cross-modal margins."""

from selfaware.bringup.models import BringupSpec, ProtocolClass
from selfaware.bringup.plausibility import check, output_cross_modal


def _analog_spec(**overrides: object) -> BringupSpec:
    fields: dict = {
        "slug": "ldr",
        "display_name": "Light sensor",
        "protocol_class": ProtocolClass.ANALOG,
        "pins": {"adc": 27},
        "expected_min": 0,
        "expected_max": 65535,
    }
    fields.update(overrides)
    return BringupSpec(**fields)


def _pulse_spec() -> BringupSpec:
    return BringupSpec(
        slug="ultrasonic",
        display_name="HC-SR04",
        protocol_class=ProtocolClass.PULSE_TIMING,
        pins={"trig": 14, "echo": 15},
        expected_min=2,
        expected_max=400,
        unit="cm",
    )


# --- analog -----------------------------------------------------------------


def test_analog_in_range_passes() -> None:
    verdict = check(_analog_spec(), "32100")
    assert verdict.passed
    assert verdict.value == 32100


def test_analog_railed_high_fails_even_inside_spec_window() -> None:
    """65535 is 'in range' 0..65535 — the rail fingerprint must still fail it."""
    verdict = check(_analog_spec(), "65535")
    assert not verdict.passed
    assert "railed high" in (verdict.reason or "")


def test_analog_railed_low_fails() -> None:
    verdict = check(_analog_spec(), "12")
    assert not verdict.passed
    assert "railed low" in (verdict.reason or "")


def test_analog_out_of_window_fails() -> None:
    verdict = check(_analog_spec(expected_min=10000, expected_max=50000), "60000")
    assert not verdict.passed
    assert "expected_max" in (verdict.reason or "")


def test_analog_rail_fingerprint_scales_to_percent_window() -> None:
    """A normalized 0..100 '%' sensor (unit='%') still trips the rails: 55 passes,
    a near-zero 0.5 rails low, and a near-full 99.7 rails high."""
    pct = dict(expected_min=0, expected_max=100, unit="%")
    assert check(_analog_spec(**pct), "55").passed
    assert "railed low" in (check(_analog_spec(**pct), "0.5").reason or "")
    assert "railed high" in (check(_analog_spec(**pct), "99.7").reason or "")


def test_unparseable_reading_fails_honestly() -> None:
    verdict = check(_analog_spec(), "<Driver object at 0x2000a1b0>")
    assert not verdict.passed
    assert "unparseable" in (verdict.reason or "")


# --- pulse timing ---------------------------------------------------------------


def test_pulse_negative_sentinel_is_no_echo_not_a_distance() -> None:
    verdict = check(_pulse_spec(), "-1")
    assert not verdict.passed
    assert "no echo" in (verdict.reason or "")


def test_pulse_in_range_passes() -> None:
    verdict = check(_pulse_spec(), "42.5")
    assert verdict.passed
    assert verdict.value == 42.5


# --- output cross-modal ------------------------------------------------------------


def test_cross_modal_clear_separation_passes() -> None:
    verdict = output_cross_modal(ambient=[100, 120, 110], driven=[5000, 5200, 5100])
    assert verdict.passed


def test_cross_modal_ratio_failure_reads_as_nothing_moved() -> None:
    verdict = output_cross_modal(ambient=[100, 120, 110], driven=[125, 130, 128])
    assert not verdict.passed
    assert "nothing moved" in (verdict.reason or "")


def test_cross_modal_needs_absolute_margin_not_just_ratio() -> None:
    # 10/2 = 5x ratio, but only +8 absolute — room-noise scale, not proof
    verdict = output_cross_modal(ambient=[1, 2], driven=[10, 12])
    assert not verdict.passed


def test_cross_modal_requires_samples() -> None:
    verdict = output_cross_modal(ambient=[], driven=[5000])
    assert not verdict.passed
