"""FastAPI entrypoint. Sets up middleware (CORS + setup gate), routers,
lifespan to init DB on startup."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import setup as setup_router
from app.api.routers import settings as settings_router
from app.db import Base, SessionLocal, engine
from app.models.app_state import AppState  # noqa
from app.models.setting import Setting  # noqa
from app.models.symbol import Symbol  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    yield


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
)


@app.middleware("http")
async def setup_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or any(path.startswith(p) for p in OPEN_PREFIXES):
        return await call_next(request)
    # Check setup state
    from app.api.routers.setup import is_setup_completed  # avoid circular
    with SessionLocal() as s:
        if is_setup_completed(s):
            return await call_next(request)
    return JSONResponse(status_code=403, content={"setup_required": True, "path": path})


app.include_router(setup_router.router)
app.include_router(settings_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}