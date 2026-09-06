"""FastAPI entrypoint. Sets up middleware (CORS + setup gate), routers,
lifespan to init DB on startup."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import pydantic
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.api.routers import ai as ai_router
from app.api.routers import ai_trader as ai_trader_router
from app.api.routers import dashboard as dashboard_router
from app.api.routers import grids as grids_router
from app.api.routers import klines as klines_router
from app.api.routers import orders as orders_router
from app.api.routers import setup as setup_router
from app.api.routers import settings as settings_router
from app.api.routers import symbols as symbols_router
from app.api.routers import trades as trades_router
from app.db import Base, SessionLocal, engine
from app.engine.lifecycle import lifecycle
from app.models.app_state import AppState  # noqa
from app.models.setting import Setting  # noqa
from app.models.symbol import Symbol  # noqa
from app.ws.realtime import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    # Configure JSON logging before anything else so even the migration /
    # create_all / wiring exceptions below land as structured records.
    # CEO plan F8: every line carries trace_id so 3-weeks-later debugging
    # is one grep away.
    from app.logging_config import configure_logging
    configure_logging()
    # Migrations run BEFORE create_all so existing installs (with no alembic)
    # pick up new columns. Each migration is idempotent — re-running on an
    # already-migrated DB is a no-op via PRAGMA table_info checks. New
    # installs also work: create_all creates the column from the model
    # definition, and the migration's PRAGMA check sees it already present.
    from app.migrations import run_all_migrations
    run_all_migrations(engine)
    Base.metadata.create_all(engine)
    await lifecycle.start()
    # Wire the AI Trader singleton with a live BinanceClient and a live
    # LLMClient if credentials are present. Missing credentials are fine —
    # the service still boots and the read endpoints keep responding.
    # BOTH clients are required for the feature to function: /dry-run guards
    # on `trader.llm and trader.broker`, and `_tick_symbol` returns early
    # unless both are set. Wiring only the broker leaves the feature inert.
    #
    # Component analysis (verified by reading the code):
    #   - get_settings() in app/config.py: constructs a pydantic-settings
    #     `Settings()`. With `extra="ignore"` and `Field(default=...)` on
    #     every field, it normally doesn't fail, but CAN raise
    #     pydantic.ValidationError if an env value doesn't coerce to the
    #     declared type (e.g. BINANCE_TESTNET="garbage").
    #   - load_secret() in app/crypto_store.py: catches
    #     `keyring.errors.KeyringError` internally and returns None — it
    #     cannot raise at runtime. (Module-import errors are `ImportError`
    #     at app import time, not in this block.)
    #   - BinanceClient.__init__ in app/broker/binance.py: stores
    #     api_key/api_secret as-is with no validation, picks base URL
    #     from two hardcoded constants by a bool, and constructs
    #     `httpx.Client(base_url=<constant>, timeout=10.0)`. With those
    #     inputs it cannot raise — auth failures are deferred to the
    #     first network call, not the constructor.
    #   - LLMClient.__init__ in app/services/llm.py: calls get_settings()
    #     (same ValidationError as above, already covered), then
    #     `(base_url or s.llm_base_url).rstrip("/")`. `Settings.llm_base_url`
    #     is `str` with `default=""`, so the `or` operand is never None and
    #     `.rstrip` cannot raise AttributeError. Unlike BinanceClient it
    #     builds NO http client in __init__ (httpx.AsyncClient is created
    #     per-call inside .chat()), so it opens no socket here and adds no
    #     new failure mode. Auth failures surface on the first .chat().
    #
    # Therefore the only LEGITIMATE, recoverable exception here is still a
    # malformed pydantic settings payload — wiring the LLM introduced no new
    # recoverable exception type, so the `except` tuple stays as-is. Any
    # other exception (AttributeError after a rename, NameError, TypeError,
    # KeyError, etc.) is a programmer error and must propagate so a typo
    # doesn't silently disable live trading.
    try:
        from app.broker.binance import BinanceClient
        from app.config import get_settings
        from app.crypto_store import load_secret
        from app.services.ai_trader.service import trader as ai_trader
        from app.services.llm import LLMClient
        cfg = get_settings()
        api_key = load_secret("api_key") or ""
        api_secret = load_secret("api_secret") or ""
        if api_key and api_secret:
            ai_trader.set_broker(
                BinanceClient(api_key, api_secret, testnet=cfg.binance_testnet)
            )
        else:
            # No creds — cold start. Service is bootable but not wired.
            ai_trader.set_broker(None)
        # LLM: keyring is canonical, env/settings is the dev fallback (same
        # precedence the broker half uses). Require both base_url and api_key
        # — that is exactly LLMClient.is_configured(), so we never hand the
        # tick loop a client whose every .chat() would raise LLMError.
        llm_base_url = load_secret("llm_base_url") or cfg.llm_base_url or ""
        llm_api_key = load_secret("llm_api_key") or cfg.llm_api_key or ""
        llm_model = load_secret("llm_model") or cfg.llm_model or None
        if llm_base_url and llm_api_key:
            ai_trader.set_llm(
                LLMClient(
                    base_url=llm_base_url, api_key=llm_api_key, model=llm_model
                )
            )
        else:
            # No LLM creds — cold start. /status reports llm_wired=False and
            # wiring_ok=False; /dry-run returns 503 until creds are added.
            ai_trader.set_llm(None)
    except (pydantic.ValidationError,):
        # Malformed env / config — recoverable, surface via logger +
        # via /status (wiring_ok=False).
        logger.exception("AI Trader broker/LLM wiring failed during lifespan")
        try:
            from app.services.ai_trader.service import trader as _ai_trader
            # `wiring_ok` is a derived read-only property on the service, so
            # there is no flag to force here — and forcing one would be a
            # lie. Clearing BOTH clients is the honest way to express "not
            # wired": it makes wiring_ok, broker_wired and llm_wired all
            # False, and it also prevents a half-wired singleton (e.g. the
            # broker landed, then get_settings() raised) from being used.
            _ai_trader.set_broker(None)
            _ai_trader.set_llm(None)
        except Exception:
            pass

    # Background tick scheduler (F1.5 / P0-2). Started regardless of wiring
    # state — when status != "running" the scheduler is a no-op that polls
    # status every second. When the user flips status to "running" via
    # /api/ai-trader/start, the next 1s wakeup starts ticking immediately.
    # This makes 24h autonomous operation actually autonomous.
    from app.services.ai_trader.scheduler import make_scheduler
    from app.services.ai_trader.service import trader as _ai_trader_for_sched
    _scheduler = make_scheduler(_ai_trader_for_sched)
    _scheduler.start()
    try:
        yield
    finally:
        await _scheduler.stop()
        await lifecycle.stop()


app = FastAPI(lifespan=lifespan, title="Binance Spot Grid Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPEN_PREFIXES = (
    "/api/setup",
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
    "/api/ai/config",
    "/api/ai-trader",
)


@app.middleware("http")
async def setup_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or any(path.startswith(p) for p in OPEN_PREFIXES):
        return await call_next(request)
    # /api/settings GET is allowed during setup (so the wizard can show current state)
    # but PUT is still gated — can't overwrite secrets before setup completes.
    if path == "/api/settings" and request.method == "GET":
        return await call_next(request)
    # Check setup state
    from app.api.routers.setup import is_setup_completed  # avoid circular
    with SessionLocal() as s:
        if is_setup_completed(s):
            return await call_next(request)
    return JSONResponse(status_code=403, content={"setup_required": True, "path": path})


app.include_router(setup_router.router)
app.include_router(settings_router.router)
app.include_router(grids_router.router)
app.include_router(klines_router.router)
app.include_router(orders_router.router)
app.include_router(trades_router.router)
app.include_router(dashboard_router.router)
app.include_router(symbols_router.router)
app.include_router(ai_router.router)
app.include_router(ai_trader_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/realtime")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive, ignore
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)