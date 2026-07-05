"""Driver author: flat schema + dynamic instructions render keyless; the
repair prompt embeds the verbatim traceback untouched; resolve_model gates on
the provider key without ever calling a provider."""

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from selfaware.agents.author import (
    ModelUnavailable,
    author_agent,
    build_author,
    render_generate_prompt,
    render_repair_prompt,
    resolve_model,
)
from selfaware.agents.deps import AuthorDeps, render_board_profile
from selfaware.agents.schemas import AttemptContext, DriverGenOutput
from selfaware.bringup.models import BringupSpec, ProtocolClass
from selfaware.config import Settings


def _spec() -> BringupSpec:
    return BringupSpec(
        slug="ldr",
        display_name="Light sensor (LDR)",
        protocol_class=ProtocolClass.ANALOG,
        pins={"adc": 27},
        expected_min=0,
        expected_max=65535,
        unit="raw",
    )


async def test_author_output_shape_with_test_model(settings: Settings) -> None:
    """TestModel synthesizes schema-valid junk -> proves the FLAT schema and
    the dynamic per-class instructions render with no model and no key."""
    deps = AuthorDeps(spec=_spec(), board_profile=render_board_profile(settings))
    result = await author_agent.run(render_generate_prompt(_spec()), deps=deps, model=TestModel())
    assert isinstance(result.output, DriverGenOutput)
    # field ORDER is load-bearing: reasoning must come first in the schema
    assert list(DriverGenOutput.model_fields) == ["reasoning", "driver_code", "imports_used"]


async def test_build_author_does_not_accumulate_request_limit_across_attempts(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for commission_crash: 'The next request would exceed the
    request_limit of 4'.

    write_driver's request_limit is a PER-ATTEMPT cap. If build_author shared one
    RunUsage across attempts, its usage.requests would accumulate and a later
    attempt would raise UsageLimitExceeded. Here the model forces one schema
    retry per attempt (2 requests each); across max_attempts a shared counter
    would cross 4 and crash. With per-attempt usage every attempt completes.
    """
    _valid = {"reasoning": "ok", "driver_code": "class Driver:\n    def read(self):\n        return 1\n", "imports_used": ""}

    def one_retry_then_valid(messages: list[ModelRequest], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0].name
        # A RetryPromptPart anywhere in the history means our earlier (empty-args)
        # tool call already failed validation once — now answer valid. Otherwise
        # return empty args to force exactly one schema-validation retry.
        retried = any(
            isinstance(p, RetryPromptPart) for m in messages for p in m.parts
        )
        args = _valid if retried else {}
        return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])

    # resolve_model() runs to build the run(model=) arg before override wins;
    # give it a key so it returns a string, then override forces FunctionModel.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    author = build_author(settings)
    with author_agent.override(model=FunctionModel(one_retry_then_valid)):
        # More attempts than the per-attempt request_limit (4): a shared counter
        # would have crashed well before this loop finished.
        for attempt_n in range(1, settings.max_attempts + 1):
            last_error = None if attempt_n == 1 else "board raised: boom"
            gen = await author(_spec(), attempt_n, last_error)
            assert gen.driver_code  # every attempt converges, none crash


def test_generate_prompt_names_the_protocol_class() -> None:
    prompt = render_generate_prompt(_spec())
    assert "analog" in prompt
    assert "GP27" in prompt


def test_repair_prompt_embeds_verbatim_traceback() -> None:
    """Invariant #1: the board's stderr goes into the prompt UNTOUCHED,
    under the canonical 'the board replied:' header."""
    traceback = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 15, in <module>\n'
        '  File "<stdin>", line 11, in read\n'
        "AttributeError: 'ADC' object has no attribute 'read'\n"
    )
    attempt = AttemptContext(
        attempt_n=2,
        previous_code="class Driver:\n    def read(self):\n        return 0\n",
        failure_kind="board_traceback",
        verbatim_error=traceback,
    )
    prompt = render_repair_prompt(_spec(), attempt)
    assert traceback in prompt  # byte-for-byte, never trimmed or paraphrased
    assert "the board replied:" in prompt
    assert attempt.previous_code in prompt


def test_resolve_model_raises_typed_error_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ModelUnavailable, match="ANTHROPIC_API_KEY"):
        resolve_model(settings)


def test_resolve_model_returns_string_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    settings = Settings(_env_file=None)
    assert resolve_model(settings) == "anthropic:claude-sonnet-5"
    # the author override wins when present
    assert resolve_model(settings, "anthropic:claude-haiku-4-5") == "anthropic:claude-haiku-4-5"


def test_resolve_model_crusoe_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """crusoe: gates on CRUSOE_API_KEY like every other provider — no key, no client."""
    monkeypatch.delenv("CRUSOE_API_KEY", raising=False)
    settings = Settings(_env_file=None, model="crusoe:moonshotai/Kimi-K2.6")
    with pytest.raises(ModelUnavailable, match="CRUSOE_API_KEY"):
        resolve_model(settings)


def test_resolve_model_crusoe_builds_openai_compatible_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the key present, crusoe: yields an OpenAIChatModel carrying the full
    `moonshotai/Kimi-K2.6` name and Crusoe's base_url — never a bare string."""
    from pydantic_ai.models.openai import OpenAIChatModel

    monkeypatch.setenv("CRUSOE_API_KEY", "test-key-not-real")
    settings = Settings(_env_file=None, model="crusoe:moonshotai/Kimi-K2.6")
    model = resolve_model(settings)
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "moonshotai/Kimi-K2.6"  # colon in the model name is preserved
    assert "api.inference.crusoecloud.com" in str(model.base_url)
