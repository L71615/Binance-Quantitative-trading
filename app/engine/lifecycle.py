"""Higher-level glue: starts/stops grid strategies, broadcasts status to WS."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from app.engine.engine import Engine
from app.strategy.base import StrategyContext
from app.strategy.grid import GridStrategy

logger = logging.getLogger(__name__)


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
            self._fire({"type": "order_placed", "payload": {"grid_id": grid_id, **kw}})
            return {"orderId": 0}

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