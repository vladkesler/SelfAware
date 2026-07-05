"""CommissionRunner — the bounded self-repair loop, the product's spine.

The control flow below is REAL code today; the single injected dependency is
the author callable (`_generate`), which PR3 wires to the PydanticAI driver
author (or the keyless mock author, or a FunctionModel-driven fake in tests).
Everything the HOST must own — attempt budget, gate, timeouts, soft reset,
event narration, plausibility verdict, registry admission — is here, in
deterministic code, exactly once.

One run = one commission = one session.exclusive() (the poller is paused
under THE lock for the duration; board.status{busy} brackets it).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from selfaware.bringup import plausibility
from selfaware.bringup.gate import GateResult, run_gate
from selfaware.bringup.harness import build_output_payload, build_read_payload
from selfaware.bringup.models import (
    AttemptRecord,
    BringupSpec,
    CommissionResult,
    CommissionStage,
    CommissionStatus,
    DriverGenOutput,
    ProtocolClass,
    StageStatus,
)
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.payloads import (
    AgentThoughtPayload,
    CommissionCodePayload,
    CommissionFailedPayload,
    CommissionPassedPayload,
    CommissionStagePayload,
    CommissionStartedPayload,
    CommissionTracebackPayload,
)
from selfaware.events.types import AgentId, DriverStatus, EventType
from selfaware.hardware.base import ExecResult
from selfaware.hardware.session import BoardSession, ExclusiveBoard
from selfaware.observability.otel import attempt_span, commission_span, stage_span
from selfaware.registry.models import DriverRecord
from selfaware.registry.store import DriverRegistry

if TYPE_CHECKING:
    from selfaware.hardware.oled_narrator import OledNarrator

# The author seam: (spec, attempt_n, last_error) -> DriverGenOutput.
# last_error is None on attempt 1; thereafter it is the VERBATIM previous
# failure (board traceback, gate reason, or plausibility verdict) — the
# repair context is rebuilt per attempt, never accumulated message history.
AuthorFn = Callable[[BringupSpec, int, str | None], Awaitable[DriverGenOutput]]


def _error_class(stderr: str) -> str:
    """Exception name off a verbatim traceback's last line, for span attributes
    (e.g. 'ValueError'). Telemetry-only — the loop itself never parses stderr."""
    last = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    name = last.split(":", 1)[0].strip()
    return name if name.isidentifier() else "unknown"


class CommissionRunner:
    """One commission = one run() call. Constructed once in the lifespan."""

    def __init__(
        self,
        session: BoardSession,
        registry: DriverRegistry,
        bus: EventBus,
        author: AuthorFn | None,
        settings: Settings,
        oled: "OledNarrator | None" = None,
    ) -> None:
        self._session = session
        self._registry = registry
        self._bus = bus
        self._author = author
        self._settings = settings
        # Optional: animate the self-repair arc on the onboard OLED. Drawn through
        # the loop's own ExclusiveBoard handle (the at-rest narrator is blocked
        # while we hold the lock) and ALWAYS failure-isolated — the display must
        # never fail a commission.
        self._oled = oled

    async def run(self, spec: BringupSpec, commission_id: str) -> CommissionResult:
        """One whole commission = one `commission` trace; attempts nest inside.

        The outer span is what the Grafana dashboard keys on
        (`{ name = "commission" }` — see docs/observability.md)."""
        with commission_span(spec.slug, spec.protocol_class.value) as span:
            result = await self._run(spec, commission_id)
            span.set_attribute("selfaware.attempts_used", len(result.attempts))
            span.set_attribute("selfaware.converged", result.status is CommissionStatus.PASSED)
            if result.failure_reason:
                span.set_attribute("selfaware.failure_reason", result.failure_reason)
            return result

    async def _run(self, spec: BringupSpec, commission_id: str) -> CommissionResult:
        """The bounded loop: generate/repair -> validate -> deploy -> test."""
        self._bus.publish(
            EventType.COMMISSION_STARTED,
            CommissionStartedPayload(
                commission_id=commission_id,
                slug=spec.slug,
                display_name=spec.display_name,
                protocol_class=spec.protocol_class,
                pins=spec.pins,
                max_attempts=self._settings.max_attempts,
            ),
        )

        attempts: list[AttemptRecord] = []
        last_error: str | None = None
        last_traceback: str | None = None

        async with self._session.exclusive() as board:
            for attempt in range(1, self._settings.max_attempts + 1):
                with attempt_span(spec.slug, spec.protocol_class.value, attempt) as span:
                    # -- generate (attempt 1) / repair (verbatim error in hand) --------
                    gen_stage = CommissionStage.GENERATE if last_error is None else CommissionStage.REPAIR
                    self._stage(commission_id, attempt, gen_stage, StageStatus.STARTED)
                    # Draw BEFORE the LLM call so "AUTHOR/MEDIC writing" shows during its latency.
                    await self._draw_oled(board, spec, attempt, gen_stage, StageStatus.STARTED)
                    with stage_span(gen_stage.value, spec.slug, attempt):
                        gen = await self._generate(spec, attempt, last_error)
                    # The agent's own words + code, on the wire BEFORE the gate:
                    # every attempt is shown, including the ones that later fail.
                    # AUTHOR writes the first draft; MEDIC repairs from the board's
                    # verbatim traceback — same LLM, two honestly-distinct roles.
                    agent_id = AgentId.AUTHOR if gen_stage is CommissionStage.GENERATE else AgentId.MEDIC
                    if gen.reasoning:
                        self._bus.publish(
                            EventType.AGENT_THOUGHT,
                            AgentThoughtPayload(agent=agent_id, text=gen.reasoning),
                        )
                    self._bus.publish(
                        EventType.COMMISSION_CODE,
                        CommissionCodePayload(
                            commission_id=commission_id,
                            attempt=attempt,
                            code=gen.driver_code,
                            is_repair=last_error is not None,
                        ),
                    )
                    self._stage(commission_id, attempt, gen_stage, StageStatus.PASSED)

                    # -- validate: the static AST gate ---------------------------------
                    self._stage(commission_id, attempt, CommissionStage.VALIDATE, StageStatus.STARTED)
                    with stage_span(CommissionStage.VALIDATE.value, spec.slug, attempt):
                        gate = self._gate(gen, spec)
                    if not gate.passed:
                        reason = gate.reason or "static gate rejected the code"
                        span.set_attribute("selfaware.gate_verdict", f"fail:{gate.violations[0].check}" if gate.violations else "fail")
                        self._stage(commission_id, attempt, CommissionStage.VALIDATE, StageStatus.FAILED, reason)
                        await self._draw_oled(board, spec, attempt, CommissionStage.VALIDATE, StageStatus.FAILED)
                        last_error = f"static gate rejected the code: {reason}"
                        attempts.append(
                            AttemptRecord(attempt=attempt, stage_reached=CommissionStage.VALIDATE, gate_reason=reason)
                        )
                        continue
                    span.set_attribute("selfaware.gate_verdict", "pass")
                    self._stage(commission_id, attempt, CommissionStage.VALIDATE, StageStatus.PASSED)

                    # -- deploy + test: ONE exec over the raw REPL (no flash writes) ---
                    # Deploy "passes" by construction once gated: exec-over-REPL means
                    # the code lands and runs in the same breath; TEST judges it.
                    self._stage(commission_id, attempt, CommissionStage.DEPLOY, StageStatus.STARTED)
                    self._stage(commission_id, attempt, CommissionStage.DEPLOY, StageStatus.PASSED)
                    self._stage(commission_id, attempt, CommissionStage.TEST, StageStatus.STARTED)
                    # "THE BOARD // RUNNING IT" — drawn before the deploy+test exec.
                    await self._draw_oled(board, spec, attempt, CommissionStage.TEST, StageStatus.STARTED)
                    with stage_span(CommissionStage.TEST.value, spec.slug, attempt):
                        result = await self._deploy_and_test(board, gen.driver_code, spec)

                    if result.timed_out:
                        # A hung driver must never wedge the line: host-owned recovery.
                        await board.soft_reset()
                        detail = "host timeout: exec did not return (possible hang) — board soft-reset"
                        span.set_attribute("selfaware.board_error_class", "timeout")
                        self._stage(commission_id, attempt, CommissionStage.TEST, StageStatus.FAILED, detail)
                        await self._draw_oled(board, spec, attempt, CommissionStage.TEST, StageStatus.FAILED)
                        last_error = detail
                        attempts.append(AttemptRecord(attempt=attempt, stage_reached=CommissionStage.TEST))
                        continue

                    if result.stderr:
                        # The un-fakeable signal: VERBATIM, never trimmed or paraphrased.
                        self._bus.publish(
                            EventType.COMMISSION_TRACEBACK,
                            CommissionTracebackPayload(
                                commission_id=commission_id,
                                attempt=attempt,
                                stage=CommissionStage.TEST,
                                traceback=result.stderr,
                            ),
                        )
                        span.set_attribute("selfaware.board_error_class", _error_class(result.stderr))
                        self._stage(commission_id, attempt, CommissionStage.TEST, StageStatus.FAILED, "board raised")
                        # "TRACEBACK // THE BOARD REJECTED IT" — the repair trigger, on the device.
                        await self._draw_oled(board, spec, attempt, CommissionStage.TEST, StageStatus.FAILED)
                        last_error = result.stderr
                        last_traceback = result.stderr
                        attempts.append(
                            AttemptRecord(attempt=attempt, stage_reached=CommissionStage.TEST, traceback=result.stderr)
                        )
                        continue

                    # -- judge: host plausibility, never the model's opinion -----------
                    verdict = self._judge(result, spec)
                    if not verdict.passed:
                        reason = verdict.reason or "implausible reading"
                        span.set_attribute("selfaware.board_error_class", "implausible")
                        self._stage(commission_id, attempt, CommissionStage.TEST, StageStatus.FAILED, reason)
                        await self._draw_oled(board, spec, attempt, CommissionStage.TEST, StageStatus.FAILED)
                        last_error = reason
                        attempts.append(
                            AttemptRecord(attempt=attempt, stage_reached=CommissionStage.TEST, reading=verdict.value)
                        )
                        continue

                    # -- PASSED: admission gate opens exactly here ----------------------
                    span.set_attribute("selfaware.reading_value", str(verdict.value))
                    span.set_attribute("selfaware.converged", True)
                    self._stage(
                        commission_id, attempt, CommissionStage.TEST, StageStatus.PASSED,
                        f"reading={verdict.value}",
                    )
                    attempts.append(
                        AttemptRecord(
                            attempt=attempt, stage_reached=CommissionStage.TEST, reading=verdict.value, passed=True
                        )
                    )
                    self._admit(spec, gen.driver_code, attempt, verdict.value)
                    self._bus.publish(
                        EventType.COMMISSION_PASSED,
                        CommissionPassedPayload(
                            commission_id=commission_id,
                            slug=spec.slug,
                            attempts_used=attempt,
                            reading=verdict.value,
                            unit=spec.unit,
                        ),
                    )
                    # "LIVE // SIGNAL ACQUIRED" — the win, on the board's own screen.
                    await self._draw_oled(board, spec, attempt, None, None, outcome="passed")
                    return CommissionResult(
                        spec=spec,
                        status=CommissionStatus.PASSED,
                        attempts=attempts,
                        final_code=gen.driver_code,
                        final_reading=verdict.value,
                    )

            # -- budget exhausted: honest failure, clean line ------------------------
            await board.soft_reset()

        failure_reason = last_error or "attempt budget exhausted"
        self._bus.publish(
            EventType.COMMISSION_FAILED,
            CommissionFailedPayload(
                commission_id=commission_id,
                slug=spec.slug,
                attempts_used=len(attempts),
                reason=failure_reason,
                last_traceback=last_traceback,
            ),
        )
        return CommissionResult(
            spec=spec,
            status=CommissionStatus.FAILED,
            attempts=attempts,
            failure_reason=failure_reason,
        )

    # --- stages ------------------------------------------------------------------

    async def _generate(self, spec: BringupSpec, attempt: int, last_error: str | None) -> DriverGenOutput:
        """The LLM's only entry point into the loop.

        PR3 wires the author agent (agents/author.py): render the per-class
        prompt + board profile + the VERBATIM last_error, run the PydanticAI
        agent, return its DriverGenOutput. Tests inject FunctionModel-driven
        fakes through the same constructor seam; `mock_author=true` injects
        the canned fail->repair->pass sequence for the keyless demo.
        """
        if self._author is None:
            raise NotImplementedError("PR3 wires the author agent (agents/author.py) via the constructor seam")
        return await self._author(spec, attempt, last_error)

    def _gate(self, gen: DriverGenOutput, spec: BringupSpec) -> GateResult:
        """Pure, instant, no hardware risk. Includes the imports_used lie detector."""
        return run_gate(gen.driver_code, spec, self._settings, imports_used=gen.imports_used)

    async def _deploy_and_test(self, board: ExclusiveBoard, code: str, spec: BringupSpec) -> ExecResult:
        """Host-authored harness + ONE exec on the already-exclusive board.

        Outputs get the try/finally set(0) payload (soft verify day-1;
        cross-modal verifier resolution from verify_with_slug is build day).
        Pulse timing gets the longer host watchdog — echo timeouts stack.
        """
        if spec.protocol_class is ProtocolClass.OUTPUT:
            payload = build_output_payload(code, spec, verify_code=None)
        else:
            payload = build_read_payload(code, spec)
        timeout = (
            self._settings.pulse_exec_timeout_s
            if spec.protocol_class is ProtocolClass.PULSE_TIMING
            else self._settings.exec_timeout_s
        )
        return await board.exec(payload, timeout)

    def _judge(self, result: ExecResult, spec: BringupSpec) -> plausibility.Verdict:
        """Host plausibility on the last stdout line (per-class predicates)."""
        return plausibility.check(spec, result.last_line)

    def _admit(self, spec: BringupSpec, code: str, attempts_used: int, reading: float | None) -> None:
        """Register (first pass) or hot-swap (re-commission) — the admission gate."""
        now = datetime.now(UTC)
        if self._registry.get(spec.slug) is not None:
            self._registry.update_code(spec.slug, code, verified_at=now, reason="recommission")
            return
        self._registry.register(
            DriverRecord(
                slug=spec.slug,
                display_name=spec.display_name,
                protocol_class=spec.protocol_class,
                driver_code=code,
                pins=spec.pins,
                unit=spec.unit,
                status=DriverStatus.ACTIVE,
                verified_at=now,
                attempts_used=attempts_used,
                last_reading=reading,
                last_read_at=now,
            )
        )

    async def _draw_oled(
        self,
        board: ExclusiveBoard,
        spec: BringupSpec,
        attempt: int,
        stage: CommissionStage | None,
        status: StageStatus | None,
        *,
        outcome: str | None = None,
        fail_reason: str | None = None,
    ) -> None:
        """Animate one commission beat on the onboard OLED, through the loop's
        own exclusive board handle. ALWAYS failure-isolated: a slow, absent, or
        broken display can never fail — or even slow — a commission."""
        if self._oled is None:
            return
        try:
            await self._oled.draw_commission(
                board,
                slug=spec.slug,
                display_name=spec.display_name,
                attempt=attempt,
                max_attempts=self._settings.max_attempts,
                stage=stage.value if stage is not None else None,
                status=status.value if status is not None else None,
                outcome=outcome,
                fail_reason=fail_reason,
            )
        except Exception:  # noqa: BLE001 — the OLED is ambience, never load-bearing
            pass

    def _stage(
        self,
        commission_id: str,
        attempt: int,
        stage: CommissionStage,
        status: StageStatus,
        detail: str = "",
    ) -> None:
        self._bus.publish(
            EventType.COMMISSION_STAGE,
            CommissionStagePayload(
                commission_id=commission_id, attempt=attempt, stage=stage, status=status, detail=detail
            ),
        )
