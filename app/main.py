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
    Base.metadata.create_all(engine)
    await lifecycle.start()
    # Wire the AI Trader singleton with a live BinanceClient if credentials
    # are present. Missing credentials are fine — the service still boots
    # and the read endpoints keep responding.
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
    #
    # Therefore the only LEGITIMATE, recoverable exception here is a
    # malformed pydantic settings payload. We narrow `except` to that
    # tuple. Any other exception (AttributeError after a rename, NameError,
    # TypeError, KeyError, etc.) is a programmer error and must propagate
    # so a typo doesn't silently disable live trading.
    try:
        from app.broker.binance import BinanceClient
        from app.config import get_settings
        from app.crypto_store import load_secret
        from app.services.ai_trader.service import trader as ai_trader
        cfg = get_settings()
        api_key = load_secret("api_key") or ""
        api_secret = load_secret("api_secret") or ""
        if api_key and api_secret:
            ai_trader.set_broker(
                BinanceClient(api_key, api_secret, testnet=cfg.binance_testnet)
            )
        else:
            # No creds — cold start. Service is bootable but not wired.
            # set_broker(None) keeps the wiring_ok flag invariant intact.
            ai_trader.set_broker(None)
    except (pydantic.ValidationError,):
        # Malformed env / config — recoverable, surface via logger +
        # via /status (wiring_ok=False).
        logger.exception("AI Trader broker wiring failed during lifespan")
        try:
            from app.services.ai_trader.service import trader as _ai_trader
            _ai_trader.wiring_ok = False
        except Exception:
            pass
    yield
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