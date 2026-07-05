"""Canonical wire strings for every event and command type.

Dot-namespaced. These enums are the single source of truth for type strings;
`frontend/src/types/events.ts` mirrors them verbatim. Never inline a type
string anywhere else in the backend.
"""

from enum import StrEnum


class EventType(StrEnum):
    """Server -> client event types."""

    # system.* — connection lifecycle and command outcomes
    SYSTEM_HELLO = "system.hello"
    SYSTEM_ACK = "system.ack"
    SYSTEM_ERROR = "system.error"

    # board.* — physical link state
    BOARD_CONNECTED = "board.connected"
    BOARD_DISCONNECTED = "board.disconnected"
    BOARD_STATUS = "board.status"

    # commission.* — the self-repair loop, narrated stage by stage
    COMMISSION_STARTED = "commission.started"
    COMMISSION_STAGE = "commission.stage"
    COMMISSION_CODE = "commission.code"
    COMMISSION_TRACEBACK = "commission.traceback"
    COMMISSION_PASSED = "commission.passed"
    COMMISSION_FAILED = "commission.failed"

    # agent.* — LLM activity, streamed. `agent` field ∈ AgentId (author|medic|pilot)
    AGENT_THOUGHT = "agent.thought"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_TOOL_RESULT = "agent.tool_result"
    AGENT_MESSAGE = "agent.message"

    # live values
    SENSOR_READING = "sensor.reading"
    ACTUATOR_STATE = "actuator.state"

    # sensor.health — derived health verdict + degradation trend (analytics/)
    SENSOR_HEALTH = "sensor.health"

    # discovery.* — plug-and-detect (I2C identity; ADC presence-only)
    DISCOVERY_DEVICE_FOUND = "discovery.device_found"
    DISCOVERY_DEVICE_LOST = "discovery.device_lost"

    # driver.* — registry changes (admission-gated, hot-swappable)
    DRIVER_REGISTERED = "driver.registered"
    DRIVER_UPDATED = "driver.updated"

    # ui.* — agent-driven presentation hints
    UI_PANEL = "ui.panel"


class CommandType(StrEnum):
    """Client -> server command types (always acked or errored by cmd_id)."""

    COMMISSION = "cmd.commission"
    READ = "cmd.read"
    SET = "cmd.set"
    CHAT = "cmd.chat"
    BOARD_SCAN = "cmd.board_scan"
    STIMULATE = "cmd.stimulate"  # mock-only: nudge a simulated sensor (liveness demo)


# --- Wire vocabulary shared with the domain layer ---------------------------
# These value sets appear inside payloads, so the contract owns them; the
# domain layer (bringup/models.py, registry/models.py) re-exports them as its
# single import point. Values are also mirrored in frontend types and in
# agents/prompts/protocol_classes/<value>.md filenames — change all together.


class ProtocolClass(StrEnum):
    """HOW the MCU physically talks to the device — names the driver skeleton."""

    ANALOG = "analog"  # one ADC read (LDR, pot, soil, gas)
    DIGITAL_BUS = "digital_bus"  # I2C/SPI conversation (SHTC3 @0x70, SSD1306 @0x3C)
    PULSE_TIMING = "pulse_timing"  # time_pulse_us choreography (HC-SR04)
    OUTPUT = "output"  # actuator: buzzer/relay/LED/motor — verified cross-modally


class CommissionStage(StrEnum):
    """The five beats of the self-repair loop, in narration order."""

    GENERATE = "generate"
    VALIDATE = "validate"
    DEPLOY = "deploy"
    TEST = "test"
    REPAIR = "repair"


class StageStatus(StrEnum):
    STARTED = "started"
    PASSED = "passed"
    FAILED = "failed"


class DriverStatus(StrEnum):
    COMMISSIONING = "commissioning"
    ACTIVE = "active"  # passed on real silicon — the ONLY status that arms tools
    FAILED = "failed"


class AgentId(StrEnum):
    """WHO is speaking on an agent.* event — the honest cast of real agents.

    AUTHOR and MEDIC are the same driver_author LLM in two genuinely different
    modes (generate vs repair); PILOT is the copilot that operates the admitted
    drivers as tools. The scan (discovery) and verify (gate/plausibility) steps
    are deterministic HOST code and are NOT agents — they carry no AgentId.
    Mirrored in frontend/src/types/events.ts (with legacy aliases
    driver_author→author, copilot→pilot for old fixtures).
    """

    AUTHOR = "author"  # writes the driver from the spec (generate stage)
    MEDIC = "medic"  # reads the verbatim traceback and rewrites (repair stage)
    PILOT = "pilot"  # operates admitted drivers as tools (read/decide/drive)
