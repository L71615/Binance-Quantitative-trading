"""Strict LLM-output JSON parser. Returns None on any failure."""
from __future__ import annotations

import json
import re
from typing import Any

VALID_ACTIONS = {"buy", "sell", "hold"}
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _strip_fences(raw: str) -> str:
    return _FENCE_RE.sub("", raw).strip()


def parse_response(
    raw: str,
    symbol_whitelist: list[str],
    min_reason: int = 5,
    max_reason: int = 200,
) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    required = {"action", "symbol", "qty", "price", "reason"}
    if not required.issubset(data.keys()):
        return None
    action = data["action"]
    if action not in VALID_ACTIONS:
        return None
    symbol = str(data["symbol"]).upper()
    if symbol not in {s.upper() for s in symbol_whitelist}:
        return None
    try:
        qty = float(data["qty"])
        price = float(data["price"])
    except (TypeError, ValueError):
        return None
    if action != "hold":
        if qty <= 0 or price <= 0:
            return None
    reason = str(data["reason"])
    if not (min_reason <= len(reason) <= max_reason):
        return None
    return {"action": action, "symbol": symbol, "qty": qty, "price": price, "reason": reason}