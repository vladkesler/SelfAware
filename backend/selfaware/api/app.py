"""create_app() — the composition root. Everything is wired HERE, once.

Boot order (each step degrades independently; the app boots in EVERY
combination of missing key/board/memory/otel — the degradation matrix):

  observability -> bus -> transport -> session.connect (best-effort) ->
  registry (+ bind to session) -> memory (connect_or_null) -> author seam
  (mock or real) -> runner + commission service -> copilot deps ->
  handlers.bind -> poller. Shutdown walks it backwards.

Mock rules (invariant #4): MockBoard ONLY when SELFAWARE_MOCK_BOARD=true —
and then loaded with the demo fail->pass script so `make demo-mock` tells the
whole story. A real board that fails discovery stays HONESTLY disconnected;
there is no silent fallback anywhere in this file.
"""

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import selfaware
from selfaware.api import handlers, rest, ws
from selfaware.api.state import AppState
from selfaware.bringup.loop import AuthorFn, CommissionRunner
from selfaware.bringup.service import CommissionService
from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.events.commands import CommandRouter
from selfaware.hardware.base import BoardTransport
from selfaware.hardware.session import BoardSession
from selfaware.observability.otel import configure_observability
from selfaware.registry.store import DriverRegistry


async def _build_transport(settings: Settings) -> BoardTransport:
    """MockBoard (explicit flag only) or SerialBoard via discovery.

    Port not found / discovery unimplemented -> a SerialBoard with no port
    that will fail connect() and leave the session honestly disconnected.
    NEVER a crash, NEVER a silent mock.
    """
    if settings.mock_board:
        from selfaware.hardware.mock_board import MockBoard, demo_fail_then_pass_script

        # deploy+test holds the stage a beat longer than the author's thinking
        # (2x pace): with the default 1.5s pace the fail -> repair -> pass arc
        # runs ~9s — narratable, instead of flashing past in under a second.
        script = demo_fail_then_pass_script(delay_s=settings.mock_pace_s * 2)
        for exchange in script:
            # Pin the demo beats to the commission's harness execs (the only
            # pre-registration code containing the host-authored read call), so
            # a board_scan or stray exec before the commission cannot eat them.
            exchange.match = r"Driver\(\)\.read\(\)"
        # The known onboard I2C bricks (0x3C OLED, 0x70 SHTC3) answer EVERY
        # scan via the persistent responder — never queued, never exhausted —
        # so discovery cards appear on the first watcher tick, before any
        # commission, and never vanish mid-demo.
        return MockBoard(script=script, scan_addrs=[0x3C, 0x70])

    from selfaware.hardware.discovery import find_board_port
    from selfaware.hardware.serial_board import SerialBoard

    port = settings.board_port
    if port == "auto":
        try:
            port = await find_board_port(settings.serial_port_glob)
        except Exception:  # noqa: BLE001 — discovery stub/unplugged board is not a boot error
            port = None
    return SerialBoard(port or "", baud=settings.serial_baud)


def create_app(settings: Settings | None = None) -> FastAPI:
    """The factory (uvicorn selfaware.api.app:create_app --factory).

    Settings are read HERE, not at import — `import selfaware.api.app` with a
    bare environment touches nothing.
    """
    app_settings = settings if settings is not None else Settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # 1. observability — first, fail-open, so agent runs are instrumented
        configure_observability(app_settings, app=app)

        # 2. the bus — every later step talks through it
        bus = EventBus()
        router = CommandRouter(bus)

        # 3. the board — explicit mock or honest best-effort serial
        transport = await _build_transport(app_settings)
        session = BoardSession(transport, bus, app_settings)
        await session.connect()  # never raises; emits board.connected/.disconnected

        # 4. the registry, late-bound into the session's poller
        registry = DriverRegistry(bus)
        session.bind_registry(registry)

        # 5. memory — one ping decides Http vs Null; nothing blocks on it later
        from selfaware.memory.client import HttpMemoryClient

        memory = await HttpMemoryClient.connect_or_null(app_settings.memory_url)

        # 6. the author seam — the ONE switch between canned theater and a real model
        author: AuthorFn
        if app_settings.mock_author:
            from selfaware.agents.mock_author import build_mock_author

            author = build_mock_author(app_settings)
        else:
            from selfaware.agents.author import build_author

            author = build_author(app_settings)

        # 7. the loop + its single door
        runner = CommissionRunner(session, registry, bus, author, app_settings)
        commissioner = CommissionService(runner, bus, memory=memory)

        # 8. copilot deps (session, never the transport — invariant #3)
        from selfaware.agents.deps import CopilotDeps

        copilot_deps = CopilotDeps(
            session=session,
            registry=registry,
            bus=bus,
            memory=memory,
            commissioner=commissioner,
            settings=app_settings,
        )

        # 9. bind the verbs, hang the state, start the ambience
        state = AppState(
            settings=app_settings,
            bus=bus,
            router=router,
            transport=transport,
            session=session,
            registry=registry,
            memory=memory,
            runner=runner,
            commissioner=commissioner,
            copilot_deps=copilot_deps,
            author=author,
        )
        app.state.selfaware = state
        handlers.bind(state)
        await session.start_poller()

        # 10. discovery — periodic I2C scan so a plugged-in device materializes
        #     as a DeviceRail card (idles harmlessly when the board is absent).
        from selfaware.hardware.watcher import DiscoveryWatcher

        watcher = DiscoveryWatcher(session, bus, app_settings)
        state.extras["watcher"] = watcher  # /ws replays its presences on connect
        await watcher.start()

        try:
            yield
        finally:
            # shutdown: reverse order, every step shielded
            with contextlib.suppress(Exception):
                await watcher.stop()  # stop scanning before the wire closes
            with contextlib.suppress(Exception):
                await session.close()  # stops the poller, closes the transport
            aclose = getattr(memory, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

    app = FastAPI(title="SelfAware", version=selfaware.__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(rest.router)
    app.include_router(ws.router)
    return app
