"""AST safety gate: accepts a clean driver, rejects every classic disaster."""

from selfaware.bringup.gate import run_gate
from selfaware.bringup.models import BringupSpec, ProtocolClass
from selfaware.config import Settings

GOOD_ANALOG = """\
import machine
import time

class Driver:
    def __init__(self):
        self.adc = machine.ADC(27)

    def read(self):
        total = 0
        for _ in range(8):
            total += self.adc.read_u16()
            time.sleep_ms(1)
        return total // 8
"""


def _spec(**overrides: object) -> BringupSpec:
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


def test_good_analog_driver_passes(settings: Settings) -> None:
    result = run_gate(GOOD_ANALOG, _spec(), settings, imports_used="machine, time")
    assert result.passed, result.reason
    assert result.violations == []
    assert result.reason is None


def test_while_loop_rejected(settings: Settings) -> None:
    code = GOOD_ANALOG.replace("for _ in range(8):", "while True:")
    result = run_gate(code, _spec(), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "no_while" for v in result.violations)


def test_open_rejected(settings: Settings) -> None:
    code = GOOD_ANALOG + "\nf = open('boot.py', 'w')\n"
    result = run_gate(code, _spec(), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "forbidden_call" and "open" in v.detail for v in result.violations)


def test_eval_rejected(settings: Settings) -> None:
    code = GOOD_ANALOG + "\nx = eval('1+1')\n"
    result = run_gate(code, _spec(), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "forbidden_call" and "eval" in v.detail for v in result.violations)


def test_esp32_atten_rejected(settings: Settings) -> None:
    """The classic RP2040 hallucination: .atten is ESP32-only and crashes."""
    code = GOOD_ANALOG.replace(
        "self.adc = machine.ADC(27)",
        "self.adc = machine.ADC(27)\n        self.adc.atten(3)",
    )
    result = run_gate(code, _spec(), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "forbidden_attr" and "atten" in v.detail for v in result.violations)


def test_non_adc_pin_rejected(settings: Settings) -> None:
    code = GOOD_ANALOG.replace("machine.ADC(27)", "machine.ADC(15)")
    result = run_gate(code, _spec(pins={"adc": 15}), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "adc_pins" and "GP15" in v.detail for v in result.violations)


def test_imports_used_lie_rejected(settings: Settings) -> None:
    """Code imports time but the model declared only machine — lie detector."""
    result = run_gate(GOOD_ANALOG, _spec(), settings, imports_used="machine")
    assert not result.passed
    assert any(v.check == "imports_match" and "'time'" in v.detail for v in result.violations)


def test_disallowed_import_rejected(settings: Settings) -> None:
    code = "import os\n" + GOOD_ANALOG
    result = run_gate(code, _spec(), settings, imports_used="os, machine, time")
    assert not result.passed
    assert any(v.check == "imports" and "'os'" in v.detail for v in result.violations)


def test_unbounded_range_rejected(settings: Settings) -> None:
    code = GOOD_ANALOG.replace("range(8)", f"range({10_000})")
    result = run_gate(code, _spec(), settings, imports_used="machine, time")
    assert not result.passed
    assert any(v.check == "bounded_for" and "cap" in v.detail for v in result.violations)


def test_syntax_error_is_instant_fail(settings: Settings) -> None:
    result = run_gate("class Driver(\n    def read(self):", _spec(), settings)
    assert not result.passed
    assert result.violations[0].check == "syntax"
    assert "SyntaxError" in (result.reason or "")


def test_missing_driver_class_rejected(settings: Settings) -> None:
    result = run_gate("import machine\nx = machine.ADC(27)\n", _spec(), settings, imports_used="machine")
    assert not result.passed
    assert any(v.check == "driver_shape" for v in result.violations)


def test_output_driver_needs_set_with_level(settings: Settings) -> None:
    code = """\
import machine

class Driver:
    def set(self):
        pass
"""
    spec = _spec(slug="buzzer", protocol_class=ProtocolClass.OUTPUT, pins={"pwm": 20}, expected_min=None, expected_max=None)
    result = run_gate(code, spec, settings, imports_used="machine")
    assert not result.passed
    assert any(v.check == "driver_shape" and "level" in v.detail for v in result.violations)
