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
    mock_pace_s: float = 1.5  # theatrical pacing for mock author/board; 0 in tests

    # --- board / serial -------------------------------------------------------
    board_port: str = "auto"  # "auto" -> discovery.find_board_port(serial_port_glob); else a literal port id
    serial_port_glob: str = "/dev/cu.usbmodem*"  # stable-id pattern (macOS); /dev/serial/by-id/* on Linux
    serial_baud: int = 115200
    exec_timeout_s: float = 8.0  # host watchdog around EVERY exec — generated code never owns time
    pulse_exec_timeout_s: float = 12.0  # pulse_timing class gets headroom (echo timeouts stack)
    connect_timeout_s: float = 5.0
    poller_interval_s: float = 1.0
    discovery_interval_s: float = 4.0  # I2C bus re-scan cadence (hotplug -> device_found)

    # --- bringup loop ----------------------------------------------------------
    max_attempts: int = 4  # bounded; then honest FAILED + soft reset
    gate_max_for_range: int = 1000  # constant for-range cap enforced by the AST gate
    author_max_tokens: int = 32768  # completion budget; reasoning models (Kimi et al.)
    #   spend heavily on thinking BEFORE emitting the driver — 2048 starves them.
    #   Generous headroom: a truncated response fails the whole attempt, and the
    #   driver itself is tiny, so the only real cost of a high cap is latency.

    # --- services (all optional; each degrades independently) -----------------
    memory_url: str = "http://localhost:8100"  # agent-memory-server; unreachable -> NullMemoryClient
    otlp_endpoint: str = "http://localhost:4318"  # grafana/otel-lgtm OTLP-HTTP; down -> spans drop silently
    sqlite_path: str = "selfaware.db"  # registry snapshot + optional sqlite-vec

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
    servo_channel: int = 1  # S1..S4 servo port on the 0x22 co-processor; NOT a GPIO (buf[1]=channel+2)
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
            BringupSpec(
                slug="fan",
                display_name="Cooling fan (DC motor)",
                protocol_class=ProtocolClass.OUTPUT,
                pins={"sda": self.pins_i2c_sda, "scl": self.pins_i2c_scl},
                i2c_addr=self.i2c_addr_motor,  # 0x22
                unit="",
                stimulus_hint="watch the fan spin",
                verify_with_slug=None,  # soft verify: set(1)/set(0) run without a traceback
                extra_context=(
                    "DC fan on the PicoBricks MOTOR DRIVER: a TB6612FNG behind an I2C "
                    "expander at address 0x22, on I2C(0, sda=GP4, scl=GP5). PicoBricks "
                    "command protocol — build a 5-byte buffer and send it with "
                    "i2c.writeto(0x22, buf, False):\n"
                    "  buf[0]=0x26; buf[1]=motor_number; buf[2]=speed; buf[3]=direction; "
                    "buf[4]=buf[1]^buf[2]^buf[3]\n"
                    "motor_number is 1 (M1) or 2 (M2); speed is a PWM byte; direction=1 runs, "
                    "speed=0 stops. The fan may be on EITHER the M1 or M2 screw terminal, so "
                    "drive BOTH channels 1 and 2 (an empty channel is harmless).\n"
                    "Implement class Driver with set(self, level), level in {0,1}:\n"
                    "  * set(0): write speed 0 to BOTH channels — reliably STOP. Assume the "
                    "driver LATCHES; this is the only off.\n"
                    "  * set(1): drive BOTH channels at a CAPPED, gentle speed — NEVER full. "
                    "Cap the speed byte at 70 (of 255) and SOFT-START (ramp up) to avoid an "
                    "inrush brown-out that resets the board (tested-safe level). Ramp with a "
                    "BOUNDED for-loop — the safety gate FORBIDS while-loops — e.g. `for duty "
                    "in range(40, 71, 10): dc(1,duty,1); dc(2,duty,1); time.sleep_ms(30)`.\n"
                    "Import only machine and time. No while, no filesystem, no reset."
                ),
            ),
            BringupSpec(
                slug="servo",
                display_name="Servo (SG90)",
                protocol_class=ProtocolClass.OUTPUT,
                pins={"sda": self.pins_i2c_sda, "scl": self.pins_i2c_scl},
                i2c_addr=self.i2c_addr_motor,  # 0x22 — servos share the co-processor with the DC motors
                unit="",
                stimulus_hint="watch the servo horn swing",
                verify_with_slug=None,  # soft verify: set(1)/set(0) run without a traceback (+ your eyes)
                extra_context=(
                    f"Positional micro-servo (SG90) on the PicoBricks MOTOR DRIVER: a TB6612 "
                    f"board with an I2C co-processor at address 0x22, on I2C(0, sda=GP{self.pins_i2c_sda}, "
                    f"scl=GP{self.pins_i2c_scl}). Servos share the DC-motor command 0x26 but on SERVO "
                    f"channels — build a 5-byte buffer and send it with i2c.writeto(0x22, buf, False):\n"
                    f"  buf[0]=0x26; buf[1]=servo_channel+2; buf[2]=0; buf[3]=angle (0..180); "
                    f"buf[4]=buf[1]^buf[2]^buf[3]\n"
                    f"This servo is on port S{self.servo_channel} => servo_channel={self.servo_channel} "
                    f"=> buf[1]={self.servo_channel + 2}.\n"
                    "Implement class Driver with set(self, level): level is a FRACTION in [0,1] mapping "
                    "to angle 0..180 => target = max(0, min(180, round(level * 180))). set(0)=0deg is the "
                    "guaranteed rest/off (the co-processor LATCHES the last angle; this is the only off); "
                    "set(1)=180deg.\n"
                    "Make the motion clearly VISIBLE: SWEEP smoothly from the last angle to the target in "
                    "small steps (never jump), so one set() call visibly travels the whole way. Track the "
                    "current angle in self.pos (initialise self.pos=0 in __init__). Sweep with a "
                    "FIXED-COUNT loop and interpolate the angle:\n"
                    "  for i in range(0, 37):        # literal bounds REQUIRED — the gate rejects range(n) with a variable\n"
                    "      a = self.pos + (target - self.pos) * i // 36\n"
                    "      self._send(a & 0xFF)      # build + i2c.writeto the 5-byte buffer for angle a\n"
                    "      time.sleep_ms(45)         # ~1.6s per full sweep — slow, smooth glide\n"
                    "  self._send(target & 0xFF)     # land exactly on target\n"
                    "  self.pos = target\n"
                    "Per-angle buffer: bytearray([0x26, servo_channel+2, 0, angle, (servo_channel+2 ^ 0 ^ angle) "
                    "& 0xFF]); send with i2c.writeto(0x22, buf, False). NO while loop (forbidden by the gate). "
                    "Import machine and time only. No filesystem, no reset."
                ),
            ),
        ]
