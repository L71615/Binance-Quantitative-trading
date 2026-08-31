"""Engine: a single asyncio loop hosting per-grid strategy tasks.
Trade updates from the WebSocket user-data stream are routed here."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyBinding:
    grid_id: int
    name: str
    on_buy_fill: Any = None
    on_sell_fill: Any = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class Engine:
    def __init__(self):
        self._running = False
        self._bindings: dict[int, StrategyBinding] = {}
        self._consumer_tasks: dict[int, asyncio.Task] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        for t in self._consumer_tasks.values():
            t.cancel()
        self._consumer_tasks.clear()
        for b in self._bindings.values():
            while not b.queue.empty():
                try:
                    b.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self._bindings.clear()
        self._running = False

    def register_strategy(
        self,
        *,
        grid_id: int,
        strategy_name: str,
        events: list,
        ctx_args: dict,
    ) -> StrategyBinding:
        b = StrategyBinding(grid_id=grid_id, name=strategy_name)

        async def _consumer():
            while True:
                ev = await b.queue.get()
                # crude routing on payload shape
                if isinstance(ev, dict) and ev.get("side") == "BUY":
                    events.append(("buy_fill", ev))
                elif isinstance(ev, dict) and ev.get("side") == "SELL":
                    events.append(("sell_fill", ev))

        self._bindings[grid_id] = b
        self._consumer_tasks[grid_id] = asyncio.create_task(_consumer())
        return b

    async def handle_trade_update(self, payload: dict) -> None:
        gid = payload.get("grid_id")
        b = self._bindings.get(gid)
        if b is None:
            return
        await b.queue.put(payload)