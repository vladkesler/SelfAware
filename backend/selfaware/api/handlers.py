"""cmd.* handlers — the verbs of the protocol, bound to AppState.

Every handler follows one shape: parse the typed command payload, do the
thing through a SERVICE (session/registry/commissioner — never the raw
transport), and answer on the bus. The CommandRouter has already ack'd and
runs us as a task; raising here becomes system.error{handler_error}, but the
paths users actually hit get named error codes instead
(docs/event-protocol.md: model_unavailable, board_offline, mock_only, ...).
"""

import ast

from selfaware.agents.author import ModelUnavailable
from selfaware.agents.copilot import copilot_agent
from selfaware.agents.streaming import run_agent_streaming
from selfaware.api.state import CURRENT_CONNECTION, AppState
from selfaware.bringup.models import BringupSpec
from selfaware.events.envelope import Command
from selfaware.events.payloads import (
    BoardScanCommand,
    ChatCommand,
    CommissionCommand,
    DeviceFoundPayload,
    ErrorPayload,
    ReadCommand,
    SetCommand,
    StimulateCommand,
)
from selfaware.events.types import AgentId, CommandType, EventType
from selfaware.hardware.discovery import I2C_SCAN_SNIPPET, KNOWN_I2C_DEVICES
from selfaware.hardware.mock_board import MockBoard
from selfaware.registry.store import DriverToolError


def bind(state: AppState) -> None:
    """Register every cmd.* handler on the router. Called once by the lifespan."""
    router = state.router
    router.register(CommandType.COMMISSION, _make_commission(state))
    router.register(CommandType.READ, _make_read(state))
    router.register(CommandType.SET, _make_set(state))
    router.register(CommandType.CHAT, _make_chat(state))
    router.register(CommandType.BOARD_SCAN, _make_board_scan(state))
    router.register(CommandType.STIMULATE, _make_stimulate(state))


def _error(state: AppState, cmd: Command, code: str, message: str, detail: str | None = None) -> None:
    state.bus.publish(
        EventType.SYSTEM_ERROR,
        ErrorPayload(code=code, message=message, cmd_id=cmd.id, detail=detail),
    )


# --- cmd.commission ---------------------------------------------------------------


def _make_commission(state: AppState):
    async def handle(cmd: Command) -> None:
        payload = CommissionCommand.model_validate(cmd.payload)
        if payload.preset_slug:
            spec = next((s for s in state.settings.default_specs() if s.slug == payload.preset_slug), None)
            if spec is None:
                _error(state, cmd, "unknown_preset", f"no preset named {payload.preset_slug!r}")
                return
        else:
            if not (payload.slug and payload.protocol_class and payload.pins):
                _error(state, cmd, "bad_spec", "full spec needs at least slug, protocol_class and pins")
                return
            spec = BringupSpec(
                slug=payload.slug,
                display_name=payload.display_name or payload.slug,
                protocol_class=payload.protocol_class,
                pins=payload.pins,
                i2c_addr=payload.i2c_addr,
                expected_min=payload.expected_min,
                expected_max=payload.expected_max,
                unit=payload.unit,
                stimulus_hint=payload.stimulus_hint,
                verify_with_slug=payload.verify_with_slug,
                extra_context=payload.extra_context,
            )
        if not state.settings.mock_author:
            # Fail BEFORE the loop starts so a missing key is one clean error,
            # not a commission.started followed by a crash event.
            try:
                from selfaware.agents.author import resolve_model

                resolve_model(state.settings, state.settings.author_model)
            except ModelUnavailable as exc:
                _error(state, cmd, "model_unavailable", str(exc))
                return
        state.commissioner.enqueue(spec)  # None => service already published commission_busy

    return handle


# --- cmd.read / cmd.set --------------------------------------------------------------


def _make_read(state: AppState):
    async def handle(cmd: Command) -> None:
        payload = ReadCommand.model_validate(cmd.payload)
        if not state.transport.connected:
            _error(state, cmd, "board_offline", "board is not connected")
            return
        try:
            await state.registry.perform_read(state.session, payload.slug)
        except DriverToolError as exc:
            _error(state, cmd, "read_failed", str(exc))

    return handle


def _make_set(state: AppState):
    async def handle(cmd: Command) -> None:
        payload = SetCommand.model_validate(cmd.payload)
        if not state.transport.connected:
            _error(state, cmd, "board_offline", "board is not connected")
            return
        try:
            # perform_set guarantees the on-board set(0) path on error and
            # publishes actuator.state{ok} either way.
            await state.registry.perform_set(state.session, payload.slug, payload.level)
        except DriverToolError as exc:
            _error(state, cmd, "set_failed", str(exc))

    return handle


# --- cmd.chat ----------------------------------------------------------------------


def _make_chat(state: AppState):
    async def handle(cmd: Command) -> None:
        payload = ChatCommand.model_validate(cmd.payload)
        conn_id = CURRENT_CONNECTION.get()
        history = state.chat_histories.get(conn_id)
        try:
            result = await run_agent_streaming(
                copilot_agent,
                payload.text,
                deps=state.copilot_deps,
                bus=state.bus,
                settings=state.settings,
                agent_name=AgentId.PILOT,
                message_history=history,
            )
        except ModelUnavailable as exc:
            _error(state, cmd, "model_unavailable", str(exc))
            return
        if result is not None:
            state.chat_histories[conn_id] = list(result.all_messages())

    return handle


# --- cmd.board_scan -------------------------------------------------------------------


def _make_board_scan(state: AppState):
    async def handle(cmd: Command) -> None:
        BoardScanCommand.model_validate(cmd.payload)
        state.bus.publish(EventType.BOARD_STATUS, state.session.board_status())
        if not state.transport.connected:
            _error(state, cmd, "board_offline", "board is not connected — nothing to scan")
            return
        snippet = I2C_SCAN_SNIPPET.format(
            sda=state.settings.pins_i2c_sda, scl=state.settings.pins_i2c_scl
        )
        result = await state.session.exec(snippet)
        if not result.ok:
            _error(state, cmd, "scan_failed", "I2C scan raised on the board", detail=result.stderr or "timeout")
            return
        try:
            addrs = ast.literal_eval(result.last_line) if result.last_line else []
        except (ValueError, SyntaxError):
            _error(state, cmd, "scan_failed", f"unparseable scan output: {result.last_line!r}")
            return
        for addr in addrs:
            known = KNOWN_I2C_DEVICES.get(addr)
            state.bus.publish(
                EventType.DISCOVERY_DEVICE_FOUND,
                DeviceFoundPayload(
                    bus="i2c",
                    addr=addr,
                    identity=known["identity"] if known else None,
                    confidence="exact" if known else "unknown",
                    suggested_spec=known["suggested_spec"] if known else None,
                ),
            )

    return handle


# --- cmd.stimulate ----------------------------------------------------------------------


def _make_stimulate(state: AppState):
    async def handle(cmd: Command) -> None:
        payload = StimulateCommand.model_validate(cmd.payload)
        if not isinstance(state.transport, MockBoard):
            _error(state, cmd, "mock_only", "cmd.stimulate only works on the mock board")
            return
        try:
            state.transport.stimulate(payload.slug, payload.delta)
        except KeyError:
            _error(state, cmd, "unknown_slug", f"no simulated sensor for slug {payload.slug!r}")

    return handle
