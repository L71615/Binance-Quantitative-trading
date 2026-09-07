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


def _base_snapshot(broker, symbol, grid_has_open_orders) -> dict[str, Any]:
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


def _futures_fields(broker, symbol) -> dict[str, Any]:
    """Add futures-only fields. Errors fall back to safe defaults so a
    partial broker outage does not block the spot-shaped snapshot."""
    out: dict[str, Any] = {}
    try:
        out["mark_price"] = float(broker.get_mark_price(symbol)["markPrice"])
    except Exception:
        out["mark_price"] = "(unavailable)"
    try:
        account = broker.get_account_info()
        out["available_margin_usdt"] = float(account.get("availableBalance", 0))
    except Exception:
        out["available_margin_usdt"] = "(unavailable)"
    try:
        positions = broker.get_position_risk(symbol)
        if positions:
            pos = positions[0]
            out["current_position_qty"] = float(pos["positionAmt"])
            out["current_position_entry_price"] = float(pos.get("entryPrice", 0))
            out["current_position_leverage"] = int(pos.get("leverage", 0))
        else:
            out["current_position_qty"] = 0
            out["current_position_entry_price"] = 0
            out["current_position_leverage"] = 0
    except Exception:
        out["current_position_qty"] = 0
    return out


def gather(
    broker, symbol: str, *, grid_has_open_orders: Callable[[str], bool],
    market_type: str = "spot",
) -> dict[str, Any]:
    """Build the snapshot dict passed into prompt.build_messages + guards.

    Spot-mode (default): keys = symbol, price, klines_summary, balances,
    open_orders, grid_has_open_orders. Matches 2026-09-01 spec.

    Futures-mode: additionally includes mark_price, available_margin_usdt,
    current_position_qty (signed), current_position_entry_price,
    current_position_leverage. These power the futures system prompt
    user-section.
    """
    snapshot = _base_snapshot(broker, symbol, grid_has_open_orders)
    if market_type == "futures":
        snapshot.update(_futures_fields(broker, symbol))
    return snapshot
