"""Settings — the ONE place for every knob and every pin number.

Nothing else in the backend hardcodes a tunable or a GPIO. Env prefix is
SELFAWARE_ (root `.env` is loaded by the Makefile / uvicorn cwd); every field
below is therefore env-overridable, which matters doubly for the pin map:
PicoBricks board revisions genuinely differ, and the UNCONFIRMED pins are
exactly why they are config values, not constants.

Import-time purity: constructing Settings() reads the environment, but merely
importing this module does nothing. Tests construct `Settings(_env_file=None)`
so a developer's .env can never leak into the suite.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from selfaware.bringup.models import BringupSpec, ProtocolClass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELFAWARE_", env_file=".env", extra="ignore")

    # --- model (ONE switch; provider-agnostic 'provider:model' string) -------
    model: str = "anthropic:claude-sonnet-5"
    author_model: str | None = None  # optional override for the driver author; falls back to `model`
    # Crusoe is OpenAI-compatible but has no pydantic-ai prefix of its own, so we
    # add a `crusoe:` one (see agents/author.py). Base URL lives here because it
    # is a knob; the CRUSOE_API_KEY is a raw env var read at run time, like every
    # other provider key (never a Settings field — provider SDKs want os.environ).
    crusoe_base_url: str = "https://api.inference.crusoecloud.com/v1/"

    # --- explicit mocks (NEVER silent fallbacks) ------------------------------
    mock_board: bool = False  # True => MockBoard everywhere; board absent otherwise = honest disconnected
    mock_author: bool = False  # True => canned DriverGenOutput sequence; full demo runs keyless

    # --- board / serial -------------------------------------------------------
    board_port: str = "auto"  # "auto" -> discovery.find_board_port(serial_port_glob); else a literal port id
    serial_port_glob: str = "/dev/cu.usbmodem*"  # stable-id pattern (macOS); /dev/serial/by-id/* on Linux
    serial_baud: int = 115200
    exec_timeout_s: float = 8.0  # host watchdog around EVERY exec — generated code never owns time
    pulse_exec_timeout_s: float = 12.0  # pulse_timing class gets headroom (echo timeouts stack)
    connect_timeout_s: float = 5.0
    poller_interval_s: float = 1.0

    # --- bringup loop ----------------------------------------------------------
    max_attempts: int = 4  # bounded; then honest FAILED + soft reset
    gate_max_for_range: int = 1000  # constant for-range cap enforced by the AST gate

    # --- services (all optional; each degrades independently) -----------------
    memory_url: str = "http://localhost:8100"  # agent-memory-server; unreachable -> NullMemoryClient
    otlp_endpoint: str = "http://localhost:4318"  # grafana/otel-lgtm OTLP-HTTP; down -> spans drop silently
    sqlite_path: str = "selfaware.db"  # registry snapshot + optional sqlite-vec

    # --- MCP transport (separate process; api/rest.py + mcp_server.py) ---------
    # Gates the two endpoints that can touch real hardware (/api/drivers/{slug}
    # /read, /set). Empty means "not configured" — those endpoints then fail
    # closed (403), never silently open. mcp_server.py is a SEPARATE process
    # (see its module docstring for why) and reads SELFAWARE_MCP_* env vars
    # directly rather than through this class; this is the only one of those
    # knobs the main backend itself needs, to check incoming requests against.
    mcp_token: str = ""

    # --- PicoBricks pin map: CONFIG VALUES, not constants ----------------------
    # Board revisions differ; flagged pins are UNCONFIRMED and must be checked
    # against the physical board on build day (docs/hardware-bringup.md).
    pins_pot: int = 26  # ADC0 — fixed by the mainboard PCB
    pins_ldr: int = 27  # ADC1
    pins_button: int = 10
    pins_relay: int = 12
    pins_buzzer: int = 20
    pins_ws2812: int = 6
    pins_dht11: int = 11  # OLDER revisions only; newer boards ship an SHTC3 on I2C @0x70 — UNCONFIRMED per rev
    pins_i2c_sda: int = 4  # I2C0
    pins_i2c_scl: int = 5
    pins_motor_a: int = 21  # revision-dependent: some revs drive motors via an I2C chip @0x22 — UNCONFIRMED
    pins_motor_b: int = 22  # UNCONFIRMED (see pins_motor_a)
    pins_ir: int = 0
    i2c_addr_oled: int = 0x3C  # SSD1306 128x64
    i2c_addr_shtc3: int = 0x70
    i2c_addr_motor: int = 0x22  # only on I2C-motor board revisions
    adc_capable_pins: tuple[int, ...] = (26, 27, 28)  # RP2040 physics; the gate validates ADC(n) against this

    def default_specs(self) -> list[BringupSpec]:
        """Pre-baked BringupSpecs for the onboard bricks — one-click presets.

        `cmd.commission {preset_slug}` and the UI's DeviceRail both resolve
        from this list, keyed by slug. Ranges are HOST plausibility windows
        (never the model's opinion); stimulus hints drive the liveness UX.
        """
        return [
            BringupSpec(
                slug="ldr",
                display_name="Light sensor (LDR)",
                protocol_class=ProtocolClass.ANALOG,
                pins={"adc": self.pins_ldr},
                expected_min=0,
                expected_max=65535,
                unit="raw",
                stimulus_hint="cover the sensor with your hand",
            ),
            BringupSpec(
                slug="pot",
                display_name="Potentiometer",
                protocol_class=ProtocolClass.ANALOG,
                pins={"adc": self.pins_pot},
                expected_min=0,
                expected_max=65535,
                unit="raw",
                stimulus_hint="turn the knob",
            ),
            BringupSpec(
                slug="shtc3",
                display_name="SHTC3 temperature/humidity",
                protocol_class=ProtocolClass.DIGITAL_BUS,
                pins={"sda": self.pins_i2c_sda, "scl": self.pins_i2c_scl},
                i2c_addr=self.i2c_addr_shtc3,
                expected_min=-10,
                expected_max=60,
                unit="degC",
                stimulus_hint="breathe on the sensor",
                extra_context=(
                    "SHTC3 is command-based (wakeup 0x3517, measure 0x7CA2) — "
                    "command WRITES, not register reads. Newer PicoBricks revisions "
                    "only; older boards have a DHT11 instead."
                ),
            ),
            BringupSpec(
                slug="ultrasonic",
                display_name="HC-SR04 ultrasonic",
                protocol_class=ProtocolClass.PULSE_TIMING,
                pins={"trig": 14, "echo": 15},
                expected_min=2,
                expected_max=400,
                unit="cm",
                stimulus_hint="wave your hand in front of the sensor",
                extra_context=(
                    "TRIG/ECHO pins are TBD — user-wired, not on the mainboard; "
                    "confirm before commissioning. Use machine.time_pulse_us with an "
                    "explicit ~30ms timeout; it returns a NEGATIVE sentinel on "
                    "timeout (no echo), it does not raise."
                ),
            ),
            BringupSpec(
                slug="buzzer",
                display_name="Buzzer",
                protocol_class=ProtocolClass.OUTPUT,
                pins={"pwm": self.pins_buzzer},
                unit="",
                stimulus_hint="",
                verify_with_slug=None,  # day-1: soft verify (loads + runs, no traceback); cross-modal later
                extra_context="Passive buzzer: steady DC is silent — drive with PWM near resonance.",
            ),
        ]
