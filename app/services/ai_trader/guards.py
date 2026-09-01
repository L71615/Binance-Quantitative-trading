"""Six hard risk guards. Sequential; first failure short-circuits run_all()."""
from __future__ import annotations

from collections import namedtuple
from typing import Any, Callable

GuardResult = namedtuple("GuardResult", "ok reason")


def _pass() -> GuardResult:
    return GuardResult(True, None)


def schema_valid(parsed: dict, ctx: dict) -> GuardResult:
    # Parser already enforced schema. This is a defense-in-depth net for
    # parsers built outside this module.
    if not isinstance(parsed, dict):
        return GuardResult(False, "schema_invalid:not_dict")
    if parsed.get("action") not in {"buy", "sell", "hold"}:
        return GuardResult(False, "schema_invalid:action")
    return _pass()


def per_order_cap(parsed: dict, ctx: dict, settings) -> GuardResult:
    if parsed["action"] == "hold":
        return _pass()
    notional = float(parsed["qty"]) * float(parsed["price"])
    cap = float(settings.max_order_quote_usdt)
    if notional > cap:
        return GuardResult(False, f"exceeds_per_order_cap: {notional:.2f} > {cap:.2f}")
    return _pass()


def position_cap(parsed: dict, ctx: dict, settings) -> GuardResult:
    if parsed["action"] != "buy":
        return _pass()  # sells always reduce exposure
    current_price = float(ctx.get("current_price", parsed["price"]))
    base_balance = float(ctx.get("base_balance", 0.0))
    projection = base_balance * current_price + float(parsed["qty"]) * float(parsed["price"])
    cap = float(settings.max_position_per_symbol_usdt)
    if projection > cap:
        return GuardResult(
            False, f"would_exceed_position_cap: {projection:.2f} > {cap:.2f}"
        )
    return _pass()


def daily_loss_cap(
    parsed: dict, ctx: dict, settings, *, pnl_so_far_today_usdt: float
) -> GuardResult:
    if pnl_so_far_today_usdt < float(settings.daily_loss_cap_usdt):
        return GuardResult(
            False,
            f"daily_loss_cap_hit: {pnl_so_far_today_usdt:.2f} < "
            f"{settings.daily_loss_cap_usdt:.2f}",
        )
    return _pass()


def daily_trade_cap(
    parsed: dict, ctx: dict, settings, *, trades_today: int
) -> GuardResult:
    if trades_today >= int(settings.daily_max_trades):
        return GuardResult(
            False,
            f"daily_trades_cap_hit: {trades_today} >= {settings.daily_max_trades}",
        )
    return _pass()


def symbol_exclusive(
    parsed: dict, ctx: dict, *, grid_has_open_orders: Callable[[str], bool]
) -> GuardResult:
    if grid_has_open_orders(parsed["symbol"]):
        return GuardResult(False, "grid_open_orders_for_symbol")
    return _pass()


def run_all(
    parsed: dict,
    ctx: dict,
    settings,
    *,
    pnl_today: float,
    trades_today: int,
    grid_has_open_orders: Callable[[str], bool],
) -> tuple[bool, list[GuardResult]]:
    steps: list[tuple[Callable, dict]] = [
        (schema_valid, {"parsed": parsed, "ctx": ctx}),
        (per_order_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (position_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (
            daily_loss_cap,
            {"parsed": parsed, "ctx": ctx, "settings": settings,
             "pnl_so_far_today_usdt": pnl_today},
        ),
        (
            daily_trade_cap,
            {"parsed": parsed, "ctx": ctx, "settings": settings,
             "trades_today": trades_today},
        ),
        (
            symbol_exclusive,
            {"parsed": parsed, "ctx": ctx,
             "grid_has_open_orders": grid_has_open_orders},
        ),
    ]
    results: list[GuardResult] = []
    for fn, kw in steps:
        r = fn(**kw)
        results.append(r)
        if not r.ok:
            return False, results
    return True, results