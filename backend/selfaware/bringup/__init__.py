"""The bounded self-repair loop and its deterministic host gates.

Spine (from the agentic-hardware-bringup methodology):

    generate -> AST gate -> deploy (exec over raw REPL, NO flash writes)
        -> test-read on real silicon -> feed the VERBATIM traceback back
        -> retry (max_attempts) -> soft reset + honest FAILED

Division of labor is law: the HOST owns the gate, the attempt budget,
timeouts, soft reset, harness code, and plausibility verdicts. The LLM only
ever fills `DriverGenOutput`. Reliability is a property of the LOOP, not the
model — which is exactly why the loop body lives here in deterministic code
and the model sits behind a single injected callable.

Deliberately no re-exports here: modules import from their exact home
(`bringup.models`, `bringup.gate`, ...) so import graphs stay legible.
"""
