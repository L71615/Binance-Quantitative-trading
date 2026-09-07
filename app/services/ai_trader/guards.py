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


# ---- Futures-specific guards (Task 5) ----

def leverage_validation(parsed: dict, ctx: dict, settings, *, broker) -> GuardResult:
    """Confirm exchange-side leverage matches settings.leverage.

    Binance's set_leverage is idempotent — calling with the current value
    is a no-op. We only call it when:
      - No position exists for this symbol yet, OR
      - Position exists but its leverage differs from settings.leverage.

    Failure mode: set_leverage raises (e.g. 403 leverage too high for
    the symbol). We trip the guard, the audit row carries the reason,
    and the operator must lower settings.leverage.
    """
    try:
        positions = broker.get_position_risk(parsed["symbol"])
        if positions:
            current_lev = int(positions[0].get("leverage", 0))
        else:
            current_lev = 0
        if current_lev != int(settings.leverage or 0):
            broker.set_leverage(parsed["symbol"], int(settings.leverage))
    except Exception as e:
        return GuardResult(
            False, f"leverage_set_failed:{type(e).__name__}:{e}"
        )
    return _pass()


def margin_check(
    parsed: dict, ctx: dict, settings,
    *, broker, account_info,
) -> GuardResult:
    """Verify required initial margin fits within available balance.

    required_margin = notional / leverage. We require it to be ≤ 80% of
    account_info['availableBalance'] — the standard "never use all your
    margin" rule. The 0.8 multiplier is hardcoded; settings field could
    be added later if needed.
    """
    if parsed["action"] == "hold":
        return _pass()
    notional = abs(float(parsed["qty"]) * float(parsed["price"]))
    leverage = max(1, int(settings.leverage or 1))
    required_margin = notional / leverage
    available = float(account_info.get("availableBalance", 0) or 0)
    if required_margin > 0.8 * available:
        return GuardResult(
            False,
            f"margin_insufficient:{required_margin:.2f} > 80% of {available:.2f}",
        )
    return _pass()


def liquidation_distance(parsed: dict, ctx: dict, settings, *, broker) -> GuardResult:
    """Verify mark price is at least 15% away from estimated liquidation.

    Pure-function liquidation estimate: long entry*(1-1/lev), short
    entry*(1+1/lev). The 15% threshold is hardcoded; documented as
    "approximate, intended as early warning" in the design spec.

    If no position exists, passes (liquidation distance is N/A).
    """
    if parsed["action"] == "hold":
        return _pass()
    try:
        sym = parsed["symbol"]
        positions = broker.get_position_risk(sym)
        if not positions:
            return _pass()
        pos = positions[0]
        pos_amt = float(pos["positionAmt"])
        if pos_amt == 0:
            return _pass()
        entry = float(pos["entryPrice"])
        mark = float(broker.get_mark_price(sym)["markPrice"])
        liq = estimate_liq_price(
            pos_amt, entry, int(settings.leverage or 1), settings.margin_type
        )
        distance_pct = abs(mark - liq) / max(mark, 1e-9) * 100
        if distance_pct < 15.0:
            return GuardResult(
                False,
                f"liquidation_too_close:{distance_pct:.2f}% < 15%",
            )
    except Exception as e:
        return GuardResult(False, f"mark_price_unavailable:{type(e).__name__}:{e}")
    return _pass()


def estimate_liq_price(
    position_amt: float, entry_price: float, leverage: int, margin_type: str
) -> float:
    """Approximate liquidation price (isolated margin formula).

    long:  liq ≈ entry * (1 - 1/leverage)
    short: liq ≈ entry * (1 + 1/leverage)

    NOT a settlement calculation — Binance's real formula includes
    maintenance margin rate + wallet balance + fees. This is an
    early-warning tripwire, not a system of record.
    """
    if position_amt == 0 or leverage <= 0 or entry_price <= 0:
        return 0.0
    if position_amt > 0:
        return entry_price * (1 - 1 / leverage)
    return entry_price * (1 + 1 / leverage)


def run_all(
    parsed: dict,
    ctx: dict,
    settings,
    *,
    pnl_today: float,
    trades_today: int,
    grid_has_open_orders: Callable[[str], bool],
    market_type: str = "spot",
    broker=None,
    account_info=None,
) -> tuple[bool, list[GuardResult]]:
    base_steps: list[tuple[Callable, dict]] = [
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
    futures_steps: list[tuple[Callable, dict]] = []
    if market_type == "futures":
        futures_steps = [
            (
                leverage_validation,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker},
            ),
            (
                margin_check,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker, "account_info": account_info},
            ),
            (
                liquidation_distance,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker},
            ),
        ]
    steps = base_steps + futures_steps
    results: list[GuardResult] = []
    for fn, kw in steps:
        r = fn(**kw)
        results.append(r)
        if not r.ok:
            return False, results
    return True, results