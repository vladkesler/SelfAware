"""The static AST safety gate — host-owned, deterministic, runs BEFORE deploy.

Necessary but NOT sufficient: static checks kill the cheap catastrophic
mistakes for free (wedged serial lines, filesystem writes, ESP32-isms), but
the decisive gate is always the real test-read on silicon. When this gate
rejects, its reason is fed back to the model as just another error signal —
one more turn of the ratchet.

Each check is a small pure function returning violations, so tests target
checks individually and build day is list-tuning, not rewiring.
"""

import ast

from pydantic import BaseModel

from selfaware.bringup.models import BringupSpec, ProtocolClass
from selfaware.config import Settings

# Per-class import allowlists: only what a driver of this class needs.
ALLOWED_IMPORTS: dict[ProtocolClass, frozenset[str]] = {
    ProtocolClass.ANALOG: frozenset({"machine", "time"}),
    ProtocolClass.DIGITAL_BUS: frozenset({"machine", "time", "struct"}),
    ProtocolClass.PULSE_TIMING: frozenset({"machine", "time"}),
    ProtocolClass.OUTPUT: frozenset({"machine", "time", "math"}),
}

# Filesystem & dynamic exec are never needed: deploy is exec-over-REPL (no
# flash writes), so banning these costs nothing and closes whole bug classes.
FORBIDDEN_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "input"})

# machine.reset/deepsleep/bootloader escape the loop; Pin.irq handlers outlive
# the exec; .atten/.width are ESP32-only ADC APIs that CRASH on RP2040 —
# models trained on ESP32/Arduino code hallucinate them constantly.
FORBIDDEN_ATTRS = frozenset({"reset", "deepsleep", "bootloader", "irq", "atten", "width"})


class GateViolation(BaseModel):
    check: str
    detail: str
    lineno: int | None = None


class GateResult(BaseModel):
    passed: bool
    reason: str | None = None  # human/LLM-readable; becomes the next attempt's error signal
    violations: list[GateViolation] = []


def run_gate(
    code: str,
    spec: BringupSpec,
    settings: Settings,
    imports_used: str | None = None,
) -> GateResult:
    """ast.parse (SyntaxError -> instant fail with the message) then all checks.

    `imports_used` is DriverGenOutput's self-declaration; None skips the lie
    detector (e.g. when re-gating registry code that has no gen output).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        violation = GateViolation(check="syntax", detail=f"SyntaxError: {exc.msg}", lineno=exc.lineno)
        return GateResult(passed=False, reason=_reason([violation]), violations=[violation])

    violations: list[GateViolation] = []
    violations += check_imports(tree, ALLOWED_IMPORTS[spec.protocol_class])
    violations += check_forbidden_calls(tree)
    violations += check_forbidden_attributes(tree)
    violations += check_no_while(tree)
    violations += check_bounded_for(tree, settings.gate_max_for_range)
    if spec.protocol_class is ProtocolClass.ANALOG:
        violations += check_adc_pins(tree, spec, settings)
    violations += check_driver_shape(tree, spec)
    if imports_used is not None:
        violations += check_imports_match(tree, imports_used)

    return GateResult(passed=not violations, reason=_reason(violations), violations=violations)


def _reason(violations: list[GateViolation]) -> str | None:
    if not violations:
        return None
    return "; ".join(f"{v.check}: {v.detail}" for v in violations)


def _imported_modules(tree: ast.Module) -> dict[str, int]:
    """Top-level module name -> first lineno, for Import and ImportFrom."""
    modules: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.setdefault(alias.name.split(".")[0], node.lineno)
        elif isinstance(node, ast.ImportFrom):
            name = (node.module or "").split(".")[0]
            modules.setdefault(name or "<relative>", node.lineno)
    return modules


def check_imports(tree: ast.Module, allowed: frozenset[str]) -> list[GateViolation]:
    """Allowlist imports to what this protocol class needs — nothing else."""
    return [
        GateViolation(
            check="imports",
            detail=f"import of {name!r} not in allowlist {sorted(allowed)}",
            lineno=lineno,
        )
        for name, lineno in _imported_modules(tree).items()
        if name not in allowed
    ]


def check_forbidden_calls(tree: ast.Module) -> list[GateViolation]:
    """open/exec/eval/compile/__import__/input — a driver never needs them."""
    return [
        GateViolation(check="forbidden_call", detail=f"call to {node.func.id}() is forbidden", lineno=node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS
    ]


def check_forbidden_attributes(tree: ast.Module) -> list[GateViolation]:
    """reset/deepsleep/bootloader/irq/atten/width, accessed anywhere.

    .atten/.width are ESP32-isms that crash RP2040 — the single most common
    model hallucination on this board, hence a named check of its own.
    """
    return [
        GateViolation(check="forbidden_attr", detail=f"attribute .{node.attr} is forbidden", lineno=node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS
    ]


def check_no_while(tree: ast.Module) -> list[GateViolation]:
    """No `while` at all — a while-True driver wedges the serial line."""
    return [
        GateViolation(check="no_while", detail="while loops are forbidden (they wedge the serial line)", lineno=node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.While)
    ]


def check_bounded_for(tree: ast.Module, max_iterations: int) -> list[GateViolation]:
    """Every `for` must iterate a constant-bounded range(...) <= the cap.

    Deliberately strict day-1 (no `for b in data:` either — averaging loops
    use range(n)); relax per-class on build day if real drivers need it.
    """
    violations: list[GateViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor)):
            continue
        it = node.iter
        if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"):
            violations.append(
                GateViolation(check="bounded_for", detail="for must iterate a constant range(...)", lineno=node.lineno)
            )
            continue
        args: list[int] = []
        constant = True
        for arg in it.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                args.append(arg.value)
            else:
                constant = False
                break
        if not constant or not args or it.keywords:
            violations.append(
                GateViolation(check="bounded_for", detail="range() bounds must be integer literals", lineno=node.lineno)
            )
            continue
        try:
            count = len(range(*args))
        except (TypeError, ValueError):
            violations.append(
                GateViolation(check="bounded_for", detail="unintelligible range() bounds", lineno=node.lineno)
            )
            continue
        if count > max_iterations:
            violations.append(
                GateViolation(
                    check="bounded_for",
                    detail=f"range iterates {count}x, over the {max_iterations} cap",
                    lineno=node.lineno,
                )
            )
    return violations


def _adc_pin_literal(call: ast.Call) -> int | None:
    """First positional arg of ADC(...): a literal int, or Pin(<literal int>)."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
        return arg.value
    if (
        isinstance(arg, ast.Call)
        and ((isinstance(arg.func, ast.Name) and arg.func.id == "Pin") or (isinstance(arg.func, ast.Attribute) and arg.func.attr == "Pin"))
        and arg.args
        and isinstance(arg.args[0], ast.Constant)
        and isinstance(arg.args[0].value, int)
    ):
        return arg.args[0].value
    return None


def check_adc_pins(tree: ast.Module, spec: BringupSpec, settings: Settings) -> list[GateViolation]:
    """ADC(n) only on ADC-capable pins — RP2040 physics, not preference.

    Run for the ANALOG class. Note the engineered demo failure ('spec points
    at a non-ADC pin -> genuine board ValueError') env-extends
    SELFAWARE_ADC_CAPABLE_PINS so the code reaches the board and the BOARD
    raises — the un-fakeable traceback, on cue.
    """
    violations: list[GateViolation] = []
    capable = set(settings.adc_capable_pins)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_adc = (isinstance(func, ast.Name) and func.id == "ADC") or (
            isinstance(func, ast.Attribute) and func.attr == "ADC"
        )
        if not is_adc:
            continue
        pin = _adc_pin_literal(node)
        if pin is None:
            violations.append(
                GateViolation(check="adc_pins", detail="ADC pin must be an integer literal", lineno=node.lineno)
            )
        elif pin not in capable:
            violations.append(
                GateViolation(
                    check="adc_pins",
                    detail=f"GP{pin} is not ADC-capable (allowed: {sorted(capable)})",
                    lineno=node.lineno,
                )
            )
    return violations


def check_driver_shape(tree: ast.Module, spec: BringupSpec) -> list[GateViolation]:
    """class Driver with read() (sensors) / set(level) (outputs) must exist.

    Output set() must take a level parameter besides self — set(level) is the
    contract that keeps actuators non-blocking and hostable in one exec.
    """
    driver = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Driver"),
        None,
    )
    if driver is None:
        return [GateViolation(check="driver_shape", detail="no `class Driver` found")]

    required = "set" if spec.protocol_class is ProtocolClass.OUTPUT else "read"
    method = next(
        (n for n in driver.body if isinstance(n, ast.FunctionDef) and n.name == required),
        None,
    )
    if method is None:
        return [
            GateViolation(
                check="driver_shape",
                detail=f"class Driver lacks a {required}() method (required for {spec.protocol_class} class)",
                lineno=driver.lineno,
            )
        ]
    if required == "set" and len(method.args.args) < 2:  # self + level
        return [
            GateViolation(check="driver_shape", detail="set() must accept a level argument", lineno=method.lineno)
        ]
    return []


def check_imports_match(tree: ast.Module, imports_used: str) -> list[GateViolation]:
    """The lie detector: every module the AST imports must be declared.

    Declared-but-unused is harmless; imported-but-undeclared means the model
    is not describing its own code accurately — reject and say so.
    """
    declared = {part.strip() for part in imports_used.split(",") if part.strip()}
    return [
        GateViolation(
            check="imports_match",
            detail=f"code imports {name!r} but imports_used declares only {sorted(declared)}",
            lineno=lineno,
        )
        for name, lineno in _imported_modules(tree).items()
        if name not in declared
    ]
