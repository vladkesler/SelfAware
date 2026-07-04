"""Verified capabilities: driver records + live hot-swappable tools.

The registry is the loop's trophy case with a bouncer: a driver enters ONLY
after a real on-board pass (admission gate, invariant #6), so every tool the
copilot ever holds is backed by verified silicon — no dead tools, no ghost
devices. Tools resolve their DriverRecord at CALL time, so a repair that
hot-swaps driver_code changes what the very next call runs.
"""
