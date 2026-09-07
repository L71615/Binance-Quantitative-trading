"""Build the (system, user) message pair sent to the LLM.

Two system templates are maintained: _SYSTEM_SPOT (unchanged from the
2026-09-01 spec) and _SYSTEM_FUTURES (new). The market_type argument
selects which one to use. The schema is identical for both — schema
validation lives in parser.parse_response regardless of market.

When futures mode is active the user message gains four fields the LLM
needs to make sensible decisions: mark price, available margin, current
position qty (signed), current position leverage.
"""
from __future__ import annotations

import json
from typing import Any

JSON_SCHEMA_TEXT = """\
Return JSON ONLY matching this schema (no markdown, no prose):
{{
  "action": "buy|sell|hold",
  "symbol": "{symbols}",
  "qty": <float, >0 if action in buy|sell>,
  "price": <float, >0 if action in buy|sell>,
  "reason": "<5-200 char rationale>"
}}
Strict JSON. If unsure, set action to "hold"."""

_SYSTEM_SPOT = """\
You are a conservative Binance Spot trader. You receive a market snapshot
and must decide one order per tick. Decisions are enforced by hard risk
guards downstream — these cannot be overridden by your output.

Constraints you MUST respect (your output is rejected if violated):
- Trade ONLY symbols from this whitelist: {symbols}.
- Spot only — never request margin, futures, or options.
- qty and price are positive decimals; use the latest close as your price reference.
- "reason" must reference concrete facts from the snapshot (price, balances,
  recent candle behaviour), not generic phrases like "I think".
- If the snapshot is ambiguous, biased toward safety, or you would do
  nothing useful, return action="hold" with an honest reason.
- Never suggest "buy all-in" or "empty the account" — guards will refuse.

Each response is audited. Quality of reasoning matters."""

_SYSTEM_FUTURES = """\
You are a conservative Binance USDⓈ-M Futures (perpetual) trader. You
receive a market snapshot and must decide one order per tick. Decisions
are enforced by hard risk guards downstream — these cannot be overridden
by your output.

Constraints you MUST respect (your output is rejected if violated):
- Trade ONLY symbols from this whitelist: {symbols}.
- This account uses FIXED leverage {leverage}x, ISOLATED margin. Do not
  request leverage changes — the operator sets it in Settings.
- Side semantics: buy = open/increase long or close short;
  sell = open/increase short or close long; hold = do nothing.
- Never suggest order quantities that would require margin exceeding
  80% of the available balance (qty * price / leverage ≤ 0.8 * available).
- Never trade if the mark price is within 15% of the estimated
  liquidation price for any existing position in the symbol.
- qty and price are positive decimals; use the latest mark price as your
  price reference for limit orders.
- "reason" must reference concrete facts from the snapshot (mark price,
  available margin, current position, recent candle behaviour), not
  generic phrases like "I think".
- If the snapshot is ambiguous, biased toward safety, or you would do
  nothing useful, return action="hold" with an honest reason.

Each response is audited. Quality of reasoning matters."""


def _user_lines_spot(snapshot: dict[str, Any]) -> list[str]:
    return [
        f"Symbol: {snapshot.get('symbol')}",
        f"Price: {snapshot.get('price')}",
        "Recent 1h klines:",
        snapshot.get("klines_summary", "(none)"),
        "Balances:",
        json.dumps(snapshot.get("balances", []), indent=2),
        "Open orders:",
        json.dumps(snapshot.get("open_orders", []), indent=2),
        f"GridTrader has open orders on this symbol: {snapshot.get('grid_has_open_orders')}",
        "Now output your decision JSON.",
    ]


def _user_lines_futures(snapshot: dict[str, Any]) -> list[str]:
    return [
        f"Symbol: {snapshot.get('symbol')}",
        f"Price: {snapshot.get('price')}",
        f"Mark price: {snapshot.get('mark_price', '(unavailable)')}",
        f"Available margin (USDT): {snapshot.get('available_margin_usdt', '(unavailable)')}",
        f"Current position qty (signed, +long/-short): {snapshot.get('current_position_qty', 0)}",
        f"Current position entry price: {snapshot.get('current_position_entry_price', '(none)')}",
        f"Current position leverage: {snapshot.get('current_position_leverage', '(none)')}x",
        "Recent 1h klines:",
        snapshot.get("klines_summary", "(none)"),
        "Balances:",
        json.dumps(snapshot.get("balances", []), indent=2),
        "Open orders:",
        json.dumps(snapshot.get("open_orders", []), indent=2),
        f"GridTrader has open orders on this symbol: {snapshot.get('grid_has_open_orders')}",
        "Now output your decision JSON.",
    ]


def build_messages(
    snapshot: dict[str, Any],
    *,
    symbols_whitelist: list[str],
    market_type: str = "spot",
    leverage: int = 1,
) -> list[dict[str, str]]:
    syms_csv = ", ".join(symbols_whitelist)
    if market_type == "futures":
        system = _SYSTEM_FUTURES.format(symbols=syms_csv, leverage=leverage)
        user_lines = _user_lines_futures(snapshot)
    else:
        system = _SYSTEM_SPOT.format(symbols=syms_csv)
        user_lines = _user_lines_spot(snapshot)
    system += "\n\n" + JSON_SCHEMA_TEXT.format(symbols=syms_csv)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]
