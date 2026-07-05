"""Sensor history, forecasting, and failure-risk scoring.

Sits alongside the registry, not inside it: the registry is the admission-
gated source of truth for "what a driver IS" (code, status, last reading);
this package is a derived, best-effort read on "what the driver's values
have been doing over time." Losing this on restart is fine (same posture as
the registry itself — see registry/store.py's docstring); losing the
registry is not.
"""
