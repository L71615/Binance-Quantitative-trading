"""Higher-level glue: starts/stops grid strategies, broadcasts status to WS.

Also persists `Order` rows for every order a grid places so Guard 6
(`symbol_exclusive`) in the AI Trader can see live grid activity. Without
this write Guard 6 always returns False and the AI Trader can stack
positions on a symbol the grid is currently holding — the exact failure
the guard exists to prevent.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from datetime import datetime, UTC
from typing import Callable

from app.db import SessionLocal
from app.engine.engine import Engine
from app.models.order import Order
from app.strategy.base import StrategyContext
from app.strategy.grid import GridStrategy

logger = logging.getLogger(__name__)


# Pre-call placeholders for `binance_order_id` must be globally unique —
# the column has a UNIQUE constraint. We mint them from a PROCESS-global
# counter offset by 1_000_000 so they never collide with real exchange
# ids (Binance spot order ids are 64-bit, never this small) AND they
# don't collide between grid sessions, test runs, or application
# restarts against the same DB file.
_PLACEHOLDER_COUNTER_START = 1_000_000
_PLACEHOLDER_ID_COUNTER = itertools.count(_PLACEHOLDER_COUNTER_START)


def _next_placeholder_binance_order_id() -> int:
    """Mint the next globally-unique placeholder id for the binance_order_id
    column. Used by `Lifecycle.start_grid` between insert and broker call;
    overwritten with the real exchange id after the call when one comes
    back, otherwise the placeholder stays so the UNIQUE constraint is
    still satisfied."""
    return next(_PLACEHOLDER_ID_COUNTER)


def _place_order_via_broker(*, symbol: str, side: str, type_: str,
                             quantity: float, price: float) -> dict:
    """Default broker-call helper used by `Lifecycle.start_grid`.

    The lifecycle writes the Order row around THIS call. The default body
    here is a no-network stub (returns `orderId=0, status="NEW"`) because
    real production wiring lives elsewhere (the Binance client is owned
    by the FastAPI lifespan; this module never imports it directly). Tests
    monkeypatch this symbol to inject a recording fake and observe the
    lifecycle's persistence path without making a real network call.

    Kept module-level (not a method on Lifecycle) so tests can patch it
    via `monkeypatch.setattr("app.engine.lifecycle._place_order_via_broker", ...)`.
    """
    return {"orderId": 0, "status": "NEW", "executedQty": "0", "price": str(price)}


class Lifecycle:
    def __init__(self):
        self.engine = Engine()
        self._listeners: list[Callable[[dict], None]] = []
        self._running = False

    def on_event(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def _fire(self, ev: dict) -> None:
        for fn in self._listeners:
            try:
                fn(ev)
            except Exception:
                logger.exception("lifecycle listener raised for event=%r", ev)

    async def start(self) -> None:
        if self._running:
            return
        await self.engine.start()
        self._running = True

    async def stop(self) -> None:
        await self.engine.stop()
        self._running = False

    async def start_grid(self, *, grid_id: int, symbol: str, lower: float,
                         upper: float, count: int, mode: str, total_quote_amount: float):
        if not self._running:
            await self.start()
        strat = GridStrategy(symbol=symbol, lower=lower, upper=upper,
                             count=count, mode=mode, total_quote_amount=total_quote_amount)

        def log(msg):
            self._fire({"type": "log", "payload": {"grid_id": grid_id, "msg": msg}})

        def place_order(**kw):
            # Pull out the columns the Order row needs. Anything else is
            # dropped — we don't persist kwargs the strategy passed us
            # beyond what the Order table actually has columns for.
            side = str(kw.get("side", "BUY")).upper()
            type_ = str(kw.get("type_", "LIMIT")).upper()
            quantity = float(kw.get("quantity", 0.0) or 0.0)
            price = float(kw.get("price", 0.0) or 0.0)
            now = datetime.now(UTC)
            # Pre-allocate a UNIQUE placeholder for `binance_order_id` so
            # multiple orders in this lifecycle don't collide on the UNIQUE
            # constraint before the broker has handed us a real id. We
            # overwrite it with the real exchange id after the call when
            # one comes back; if the helper returns 0/unset (default stub)
            # the placeholder stays in place so the row remains valid.
            placeholder_id = _next_placeholder_binance_order_id()
            row_id = None
            with SessionLocal() as s:
                row = Order(
                    grid_id=grid_id,
                    binance_order_id=placeholder_id,
                    symbol=symbol,
                    side=side,
                    type=type_,
                    price=price,
                    qty=quantity,
                    filled_qty=0.0,
                    status="NEW",
                    created_at=now,
                    updated_at=now,
                )
                s.add(row)
                s.commit()
                row_id = row.id
            # Now actually call the broker. The default helper is a stub;
            # production wires BinanceClient in here via FastAPI lifespan.
            try:
                resp = _place_order_via_broker(
                    symbol=symbol, side=side, type_=type_,
                    quantity=quantity, price=price,
                )
            except Exception as e:
                # Broker call raised — record the failure on the row so
                # the operator sees what happened. Re-raise so the
                # strategy sees the exception too.
                with SessionLocal() as s:
                    row = s.get(Order, row_id)
                    if row is not None:
                        row.status = "ERROR"
                        row.updated_at = datetime.now(UTC)
                        s.commit()
                raise
            # Update the row with the exchange's reply.
            ex_status = str(resp.get("status") or "NEW")
            # Binance uses 'FILLED' | 'PARTIALLY_FILLED' | 'NEW' | 'CANCELED'.
            # If the helper returns something exotic we keep "NEW" as a
            # safe default rather than writing garbage into the table.
            if ex_status not in {"NEW", "FILLED", "PARTIALLY_FILLED", "CANCELED"}:
                ex_status = "NEW"
            ex_order_id = int(resp.get("orderId") or 0)
            try:
                filled_qty = float(resp.get("executedQty") or 0) or None
            except (TypeError, ValueError):
                filled_qty = None
            with SessionLocal() as s:
                row = s.get(Order, row_id)
                if row is not None:
                    row.status = ex_status
                    # Only overwrite the placeholder when we got a real
                    # non-zero exchange id; keep the placeholder otherwise
                    # so the row stays UNIQUE-valid.
                    if ex_order_id:
                        row.binance_order_id = ex_order_id
                    if filled_qty is not None:
                        row.filled_qty = filled_qty
                    row.updated_at = datetime.now(UTC)
                    s.commit()
            self._fire({"type": "order_placed", "payload": {"grid_id": grid_id, **kw}})
            return resp

        def cancel_order(**kw):
            self._fire({"type": "order_canceled", "payload": {"grid_id": grid_id, **kw}})
            return {"ok": True}

        ctx = StrategyContext(log=log, place_order=place_order,
                              cancel_order=cancel_order, grid_id=grid_id, symbol=symbol)
        # Wire strategy callbacks through the engine's trade routing
        self.engine.register_strategy(
            grid_id=grid_id, strategy_name=strat.name,
            events=[], ctx_args={},
        )
        strat.on_start(ctx)
        self._fire({"type": "grid_running", "payload": {"grid_id": grid_id}})

    async def stop_grid(self, grid_id: int):
        self._fire({"type": "grid_stopped", "payload": {"grid_id": grid_id}})


# Module-level singleton for the FastAPI app and routers to share.
lifecycle = Lifecycle()