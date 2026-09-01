"""Build a market snapshot for the AI Trader LLM prompt."""
from __future__ import annotations

from typing import Any, Callable


def summarize_klines(klines: list[list[Any]]) -> str:
    """Compact human-readable summary of last N candles."""
    if not klines:
        return "no recent klines available"
    lines = []
    for k in klines[-30:]:
        # Binance kline format: [open_time, open, high, low, close, volume, ...]
        o, h, l, c, v = k[1], k[2], k[3], k[4], k[5]
        lines.append(f"O{o} H{h} L{l} C{c} V{v}")
    return " | ".join(lines)


def _last_close_or_zero(klines: list[list[Any]]) -> float:
    if not klines:
        return 0.0
    try:
        return float(klines[-1][4])
    except (ValueError, IndexError):
        return 0.0


def gather(
    broker, symbol: str, *, grid_has_open_orders: Callable[[str], bool]
) -> dict[str, Any]:
    """Collect price, klines summary, balances, open orders.

    Injected `grid_has_open_orders` lets the caller route to the live
    GridTrader state without coupling this module to the DB.
    """
    klines = broker.get_klines(symbol, "1h", limit=30)
    info = broker.get_account_info() or {}
    balances = info.get("balances", []) or []
    open_orders = broker.get_open_orders(symbol=None) or []
    return {
        "symbol": symbol,
        "price": _last_close_or_zero(klines),
        "klines_summary": summarize_klines(klines),
        "balances": balances,
        "open_orders": open_orders,
        "grid_has_open_orders": bool(grid_has_open_orders(symbol)),
    }
