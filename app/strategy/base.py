"""Strategy abstract base. Inspired by Freqtrade's IStrategy callbacks
but kept deliberately small. We only READ freqtrade for ideas — no code reuse."""
from __future__ import annotations

from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class StrategyContext:
    """Runtime services a strategy uses. Wired by the engine."""
    log: Callable[[str], None] = field(default=lambda msg: None)
    place_order: Callable[..., dict] = field(default=lambda **_: {})
    cancel_order: Callable[..., dict] = field(default=lambda **_: {})
    grid_id: int | None = None
    symbol: str = ""


class BaseStrategy(ABC):
    name: str = "base"
    symbol: str = ""

    def on_start(self, ctx: StrategyContext) -> None: ...
    def on_tick(self, ctx: StrategyContext, last_price: float) -> None: ...
    def on_order_filled(self, ctx: StrategyContext, trade: dict) -> None: ...
    def on_order_rejected(self, ctx: StrategyContext, order: dict, err: str) -> None: ...
    def on_stop(self, ctx: StrategyContext) -> None: ...
