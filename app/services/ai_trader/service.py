"""AI Trader service: state machine + tick loop. Pairs with binance.py + llm.py."""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, UTC
from typing import Any, Callable

from app.db import SessionLocal
from app.models.ai_settings import AISettings, load_or_create


_LIVE_CONFIRM = "I UNDERSTAND REAL MONEY"

def _is_live_mode() -> bool:
    # Lazy import to avoid hard dependency at import time (tests may not have
    # .env seeded).
    try:
        from app.config import get_settings
        return not bool(get_settings().binance_testnet)
    except Exception:
        return False


class AITraderService:
    def __init__(
        self,
        *,
        llm: Any | None = None,
        broker: Any | None = None,
        db_session_factory: Callable | None = None,
        grid_has_open_orders: Callable[[str], bool] | None = None,
    ):
        self.llm = llm
        self.broker = broker
        self._session_factory = db_session_factory or SessionLocal
        self.grid_has_open_orders = grid_has_open_orders or (lambda s: False)

    # ---- status helpers -----------------------------------------------
    def _settings(self) -> AISettings:
        with self._session_factory() as s:
            return load_or_create(s)

    def _set_status(self, status: str, reason: str | None = None) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = status
            row.status_reason = reason
            row.updated_at = datetime.now(UTC)
            s.commit()

    def status(self) -> dict[str, Any]:
        with self._session_factory() as s:
            row = load_or_create(s)
            return {
                "status": row.status,
                "status_reason": row.status_reason,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "last_tick_at": row.last_tick_at.isoformat() if row.last_tick_at else None,
                "max_order_quote_usdt": row.max_order_quote_usdt,
                "max_position_per_symbol_usdt": row.max_position_per_symbol_usdt,
                "daily_loss_cap_usdt": row.daily_loss_cap_usdt,
                "daily_max_trades": row.daily_max_trades,
                "symbols": row.symbol_list,
                "poll_interval_sec": row.poll_interval_sec,
                "armed_for_live_at": (
                    row.armed_for_live_at.isoformat() if row.armed_for_live_at else None
                ),
            }

    # ---- transitions ---------------------------------------------------
    async def start(self, *, confirm_text: str | None = None) -> dict:
        if _is_live_mode():
            with self._session_factory() as s:
                row = load_or_create(s)
                if row.armed_for_live_at is None:
                    if confirm_text != _LIVE_CONFIRM:
                        return {
                            "ok": False,
                            "error": "live_arming_required",
                            "required_confirm_text": _LIVE_CONFIRM,
                        }
                    row.armed_for_live_at = datetime.now(UTC)
                    # First-time live: conservative caps.
                    row.max_order_quote_usdt = min(
                        row.max_order_quote_usdt, 20.0
                    )
                    row.daily_loss_cap_usdt = max(row.daily_loss_cap_usdt, -10.0)
                    row.daily_max_trades = min(row.daily_max_trades, 10)
                    s.commit()
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = "running"
            row.enabled = True
            if row.started_at is None:
                row.started_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            s.commit()
        return {"ok": True, "status": "running"}

    # sync wrapper for tests / sync callers
    def start_sync(self, **kw) -> dict:
        return asyncio.run(self.start(**kw))

    def pause(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status == "running":
                row.status = "paused"
                row.updated_at = datetime.now(UTC)
                s.commit()

    def resume(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status in {"paused", "error"}:
                row.status = "running"
                row.status_reason = None
                row.updated_at = datetime.now(UTC)
                s.commit()

    def emergency_stop(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = "stopped"
            row.status_reason = "emergency_stopped"
            row.updated_at = datetime.now(UTC)
            s.commit()

    def reset(self, *, confirm_text: str | None = None) -> dict:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status != "stopped":
                return {"ok": False, "error": "not_stopped"}
            row.status = "idle"
            row.status_reason = None
            row.updated_at = datetime.now(UTC)
            s.commit()
        return {"ok": True, "status": "idle"}

    # ---- tick loop (placeholder here; full impl in next task) --------
    async def tick(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status != "running":
                return
            row.last_tick_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            s.commit()
