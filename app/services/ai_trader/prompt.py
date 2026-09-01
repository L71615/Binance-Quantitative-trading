"""Build the (system, user) message pair sent to the LLM."""
from __future__ import annotations

import json
from typing import Any

# Schema is provided both in the system prompt (for the LLM to read) and
# enforced downstream by parser.parse_response.
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

_SYSTEM_TEMPLATE = """\
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

Each response is audited. Quality of reasoning matters.
"""


def build_messages(snapshot: dict[str, Any], *, symbols_whitelist: list[str]) -> list[dict[str, str]]:
    syms_csv = ", ".join(symbols_whitelist)
    system = _SYSTEM_TEMPLATE.format(symbols=syms_csv)
    system += "\n\n" + JSON_SCHEMA_TEXT.format(symbols=syms_csv)
    user_lines = [
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
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]
