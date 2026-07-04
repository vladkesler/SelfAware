"""Owning the wire: raw-REPL framing, THE single lock, mock parity.

Layering law (invariant #3): nothing outside this package ever receives the
raw transport. SerialBoard and MockBoard are interchangeable behind
`base.BoardTransport`; everyone else — copilot deps, registry toolset,
poller, handlers, commission loop — goes through `session.BoardSession`,
which holds the one asyncio.Lock that serializes all board access.

Only `serial_board.py` may import pyserial, and only lazily inside methods:
the test suite runs with pyserial installed but must never open a port.
"""
