"""DriverAuthor — the agent that fills DriverGenOutput, and nothing else.

No tools (the author never touches the board — host/LLM split, invariant #2),
no message_history (repair context is rebuilt per attempt from AttemptContext,
so every attempt is one small reproducible request). The agent is constructed
WITHOUT a model; `resolve_model()` picks the model per run (a provider:model
string, or a Model instance for custom endpoints like Crusoe) and raises a typed
ModelUnavailable when the provider key is absent — callers turn that into
system.error{model_unavailable}, never a crash.

`write_driver()` is the ONLY entry point the commission loop uses;
`build_author()` adapts it to the loop's injected-callable seam
(bringup/loop.py AuthorFn), tracking previous code across attempts so the
repair prompt can show it.
"""

import os
from functools import lru_cache

from pydantic_ai import Agent, ModelSettings, UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage

from selfaware.agents.deps import AuthorDeps, render_board_profile
from selfaware.agents.prompts import load_prompt
from selfaware.agents.schemas import AttemptContext, DriverGenOutput, classify_failure
from selfaware.bringup.models import BringupSpec, ProtocolClass
from selfaware.config import Settings

try:  # pydantic-ai >= 2: RunContext at top level
    from pydantic_ai import RunContext
except ImportError:  # pragma: no cover - version drift guard
    from pydantic_ai.tools import RunContext  # type: ignore[no-redef]


class ModelUnavailable(Exception):
    """The configured model cannot run: its provider key env var is absent.

    Deliberately checked HERE, per run, instead of letting the provider SDK
    throw a wall of HTTP noise mid-commission — the caller maps this to a
    clean system.error{code: model_unavailable}.
    """


# provider prefix -> the env var whose presence means "this model can run".
# Prefixes not listed are assumed keyless-or-self-authed (ollama, test, bedrock
# via ambient AWS creds) and fall through to the provider's own error path.
PROVIDER_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google-gla": "GOOGLE_API_KEY",
    "google-vertex": "GOOGLE_APPLICATION_CREDENTIALS",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "CO_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",
    "crusoe": "CRUSOE_API_KEY",  # OpenAI-compatible endpoint; see _crusoe_model()
}


@lru_cache(maxsize=8)
def _crusoe_model(name: str, base_url: str, api_key: str) -> Model:
    """Build (once, then cache) an OpenAI-compatible Model pointed at Crusoe.

    Crusoe Cloud has no dedicated pydantic-ai prefix, but its inference API
    speaks the Chat Completions wire format — so any model it hosts (e.g.
    `moonshotai/Kimi-K2.6`) is an OpenAIChatModel behind an OpenAIProvider that
    carries the base_url + key. lru_cache keys on (model, endpoint, key) so this
    long-running server reuses ONE AsyncOpenAI client per distinct config
    instead of leaking a socket pool on every commission attempt.

    strict tool definitions are disabled: `strict` is OpenAI's own schema
    extension and Crusoe-hosted open models don't honor it, while BOTH agents
    here depend on tool-calling working — the author's structured DriverGenOutput
    and the copilot's toolbelt.
    """
    return OpenAIChatModel(
        name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        profile=OpenAIModelProfile(openai_supports_strict_tool_definition=False),
    )


def resolve_model(settings: Settings, override: str | None = None) -> str | Model:
    """The per-run model switch. Returns a pydantic-ai model string, or a Model
    instance for providers (Crusoe) that need a custom endpoint.

    Raises ModelUnavailable when the 'provider:' prefix maps to a key env var
    that is not set. Called at RUN time only — importing agent modules never
    reads credentials nor builds a client (invariant #7).
    """
    model = override or settings.model
    prefix = model.split(":", 1)[0] if ":" in model else model
    key_var = PROVIDER_KEY_ENV.get(prefix)
    if key_var is not None and not os.environ.get(key_var):
        raise ModelUnavailable(
            f"model {model!r} needs {key_var} which is not set — "
            "export it, pick another SELFAWARE_MODEL, or run with SELFAWARE_MOCK_AUTHOR=true"
        )
    if prefix == "crusoe":
        # key_var check above guarantees CRUSOE_API_KEY is present and non-empty.
        return _crusoe_model(model.split(":", 1)[1], settings.crusoe_base_url, os.environ["CRUSOE_API_KEY"])
    return model


author_agent: Agent[AuthorDeps, DriverGenOutput] = Agent(
    # model deliberately omitted — resolved per run (keyless import, TestModel-friendly)
    deps_type=AuthorDeps,
    output_type=DriverGenOutput,
    name="driver_author",
    retries=2,  # schema-validation retries only; the LOOP owns repair retries
    instructions=load_prompt("author_system.md"),
    model_settings=ModelSettings(temperature=0.2, max_tokens=2048),
)


@author_agent.instructions
def _protocol_class_guidance(ctx: RunContext[AuthorDeps]) -> str:
    """Inject the per-class fragment + board reality — steer AND catch: every
    landmine named here is also an AST-gate rule (bringup/gate.py)."""
    fragment = load_prompt(f"protocol_classes/{ctx.deps.spec.protocol_class.value}.md")
    return f"{fragment}\n{ctx.deps.board_profile}"


# --- prompt rendering (pure functions; unit-tested without a model) -----------


def render_spec(spec: BringupSpec) -> str:
    """One canonical text block describing the device — the ONLY way a spec
    enters a prompt, so prompt and domain model can never drift."""
    pins = ", ".join(f"{role}=GP{gpio}" for role, gpio in spec.pins.items())
    lines = [
        f"Device: {spec.display_name} (slug: {spec.slug})",
        f"Protocol class: {spec.protocol_class.value}",
        f"Pins: {pins}",
    ]
    if spec.i2c_addr is not None:
        lines.append(f"I2C address: {spec.i2c_addr:#04x}")
    if spec.expected_min is not None or spec.expected_max is not None:
        lo = "-inf" if spec.expected_min is None else f"{spec.expected_min:g}"
        hi = "+inf" if spec.expected_max is None else f"{spec.expected_max:g}"
        lines.append(f"Host plausibility window: {lo}..{hi} {spec.unit}".rstrip())
    elif spec.unit:
        lines.append(f"Unit: {spec.unit}")
    if spec.extra_context:
        lines.append(f"Notes: {spec.extra_context}")
    return "\n".join(lines)


def _method_contract(spec: BringupSpec) -> str:
    if spec.protocol_class is ProtocolClass.OUTPUT:
        return "a non-blocking set(level) that configures the hardware and returns"
    return "read() returning a single number"


def render_generate_prompt(spec: BringupSpec, few_shot: str = "") -> str:
    """author_generate.md -> the first-attempt user prompt."""
    few_shot_block = f"\nA driver that worked for a similar device:\n\n```python\n{few_shot}\n```\n" if few_shot else ""
    return load_prompt("author_generate.md").format(
        spec_block=render_spec(spec),
        few_shot_block=few_shot_block,
        method_contract=_method_contract(spec),
    )


def render_repair_prompt(spec: BringupSpec, attempt: AttemptContext) -> str:
    """author_repair.md -> a repair prompt embedding verbatim_error UNTOUCHED.

    str.format substitutes into the template only — the error text itself is
    inserted as-is, never trimmed, wrapped, or paraphrased (invariant #1).
    """
    return load_prompt("author_repair.md").format(
        attempt_n=attempt.attempt_n,
        spec_block=render_spec(spec),
        previous_code=attempt.previous_code or "(previous code unavailable)",
        failure_kind=attempt.failure_kind,
        verbatim_error=attempt.verbatim_error,
        method_contract=_method_contract(spec),
    )


# --- the loop's entry points ---------------------------------------------------


async def write_driver(
    spec: BringupSpec,
    deps: AuthorDeps,
    settings: Settings,
    attempt: AttemptContext | None = None,
    usage: RunUsage | None = None,
) -> DriverGenOutput:
    """One authoring attempt = one model request (plus schema retries).

    Non-streaming on purpose: structured-output JSON deltas are useless to the
    UI; the loop narrates via commission.* events and agent.thought instead.
    `usage` may be shared across a commission's attempts so the whole run has
    one budget.
    """
    prompt = (
        render_generate_prompt(spec, deps.few_shot)
        if attempt is None
        else render_repair_prompt(spec, attempt)
    )
    result = await author_agent.run(
        prompt,
        deps=deps,
        model=resolve_model(settings, settings.author_model),
        usage=usage,
        usage_limits=UsageLimits(request_limit=4),  # 1 request + schema retries, never a loop
    )
    return result.output


def build_author(settings: Settings):
    """Adapt write_driver to the loop's AuthorFn seam
    ((spec, attempt_n, last_error) -> DriverGenOutput).

    Stateful closure: remembers the code it last produced so the repair prompt
    can show it (the seam itself carries only the error string), and shares
    one RunUsage across a commission's attempts.
    """
    board_profile = render_board_profile(settings)
    previous_code = ""
    usage = RunUsage()

    async def author(spec: BringupSpec, attempt_n: int, last_error: str | None) -> DriverGenOutput:
        nonlocal previous_code
        deps = AuthorDeps(spec=spec, board_profile=board_profile)
        attempt = None
        if last_error is not None:
            attempt = AttemptContext(
                attempt_n=attempt_n,
                previous_code=previous_code,
                failure_kind=classify_failure(last_error),
                verbatim_error=last_error,
            )
        gen = await write_driver(spec, deps, settings, attempt=attempt, usage=usage)
        previous_code = gen.driver_code
        return gen

    return author
