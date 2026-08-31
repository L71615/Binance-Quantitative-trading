"""FastAPI entrypoint. Sets up middleware (CORS + setup gate), routers,
lifespan to init DB on startup."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import ai as ai_router
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