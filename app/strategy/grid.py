"""Spot grid strategy. Two-sided initial orders; later replacements are
fired on trade callbacks (engine-driven)."""
from __future__ import annotations

import math
from typing import Literal

from app.strategy.base import BaseStrategy, StrategyContext

Mode = Literal["arithmetic", "geometric"]


def build_grid_levels(lower: float, upper: float, count: int, mode: Mode = "arithmetic") -> list[float]:
    if count < 2:
        raise ValueError("count must be >= 2")
    if lower <= 0 or upper <= 0 or upper <= lower:
        raise ValueError("invalid bounds")
    if mode == "arithmetic":
        step = (upper - lower) / (count - 1)
        return [lower + step * i for i in range(count)]
    # geometric
    ratio = (upper / lower) ** (1 / (count - 1))
    return [lower * (ratio ** i) for i in range(count)]


def _round_to(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(round(value / step) * step, 10)


class GridStrategy(BaseStrategy):
    def __init__(
        self,
        symbol: str,
        lower: float,
        upper: float,
        count: int,
        mode: Mode = "arithmetic",
        total_quote_amount: float = 0.0,
        tick_size: float = 0.01,
        step_size: float = 0.0001,
    ):
        self.symbol = symbol
        self.lower = lower
        self.upper = upper
        self.count = count
        self.mode = mode
        self.total_quote_amount = total_quote_amount
        self.tick_size = tick_size
        self.step_size = step_size
        self.name = f"grid-{symbol}-{count}"
        self.levels = build_grid_levels(lower, upper, count, mode)
        self.quote_per_buy = (total_quote_amount / max(1, count // 2)) if total_quote_amount else 0.0

    def _place_two_sided(self, ctx: StrategyContext, current_price: float) -> None:
        # Buy side: nearest 3 levels below current price
        buys = [lv for lv in self.levels if lv < current_price]
        sells = [lv for lv in self.levels if lv > current_price]
        for lv in buys[-3:]:
            qty = self._qty_for_quote(lv)
            ctx.place_order(symbol=self.symbol, side="BUY", type_="LIMIT",
                            quantity=qty, price=_round_to(lv, self.tick_size))
        for lv in sells[:3]:
            qty = self._qty_for_quote(lv)
            ctx.place_order(symbol=self.symbol, side="SELL", type_="LIMIT",
                            quantity=qty, price=_round_to(lv, self.tick_size))

    def _qty_for_quote(self, price: float) -> float:
        if self.quote_per_buy <= 0:
            return self.step_size
        qty = self.quote_per_buy / price
        return max(self.step_size, _round_to(qty, self.step_size))

    def on_start(self, ctx: StrategyContext) -> None:
        current_price = (self.lower + self.upper) / 2
        self._place_two_sided(ctx, current_price)
        ctx.log(f"grid started for {self.symbol} between {self.lower} and {self.upper}")

    def on_tick(self, ctx: StrategyContext, last_price: float) -> None:
        # Future work: re-center / pause if outside bounds.
        return None

    def on_order_filled(self, ctx: StrategyContext, trade: dict) -> None:
        """On BUY fill, place a SELL one tick above; on SELL fill, place BUY one tick below."""
        side = trade.get("side")
        price = float(trade.get("price") or 0)
        qty = float(trade.get("qty") or 0)
        if not price or not qty:
            return
        if side == "BUY":
            new_price = _round_to(price + self.tick_size, self.tick_size)
            if new_price <= self.upper:
                ctx.place_order(symbol=self.symbol, side="SELL", type_="LIMIT",
                                quantity=qty, price=new_price)
        elif side == "SELL":
            new_price = _round_to(price - self.tick_size, self.tick_size)
            if new_price >= self.lower:
                ctx.place_order(symbol=self.symbol, side="BUY", type_="LIMIT",
                                quantity=qty, price=new_price)

    def on_order_rejected(self, ctx: StrategyContext, order: dict, err: str) -> None:
        ctx.log(f"order rejected: {order} err={err}")

    def on_stop(self, ctx: StrategyContext) -> None:
        ctx.log(f"grid stopped for {self.symbol}")