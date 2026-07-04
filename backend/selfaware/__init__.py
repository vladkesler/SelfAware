"""SelfAware — verified hands for AI agents in the physical world.

Plug in a device nobody wrote a driver for, teach it once, and an AI agent
writes the MicroPython driver, deploys it to a real Pico W over USB serial
(raw REPL, no flash writes), test-reads it on real silicon, and self-repairs
from the board's own verbatim traceback. Drivers that survive the loop are
admitted to the registry and become live tools an agent copilot can call.

Package map (see docs/architecture.md):
    events/        the typed language of the system (WS envelopes, bus, commands)
    hardware/      owning the wire: raw REPL framing, THE single lock, mock parity
    bringup/       the bounded self-repair loop and its deterministic host gates
    agents/        the LLM roles: driver author + dashboard copilot
    registry/      verified capabilities: records + live hot-swappable tools
    memory/        optional cross-session memory (degrades to no-op)
    observability/ spans/logs to local Grafana LGTM (fail-open)
    api/           FastAPI wiring: one WebSocket, tiny REST, lifespan
"""

__version__ = "0.1.0"
PROTOCOL_VERSION = 1
