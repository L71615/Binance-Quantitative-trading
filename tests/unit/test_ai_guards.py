import pytest

from app.services.ai_trader.guards import (
    GuardResult,
    daily_loss_cap,
    daily_trade_cap,
    per_order_cap,
    position_cap,
    run_all,
    schema_valid,
    symbol_exclusive,
)

SET = type("S", (), {
    "max_order_quote_usdt": 50.0,
    "max_position_per_symbol_usdt": 500.0,
    "daily_loss_cap_usdt": -30.0,
    "daily_max_trades": 20,
})()


def parsed_buy(qty=0.001, price=60000, symbol="BTCUSDT"):
    return {"action": "buy", "symbol": symbol, "qty": qty, "price": price, "reason": "breakout retest"}


def parsed_sell(qty=0.001, price=60000, symbol="BTCUSDT"):
    return {"action": "sell", "symbol": symbol, "qty": qty, "price": price, "reason": "take profit"}


def parsed_hold():
    return {"action": "hold", "symbol": "BTCUSDT", "qty": 0.0, "price": 0.0, "reason": "no setup right now"}


def test_schema_valid_hold_is_fine():
    r = schema_valid(parsed_hold(), {})
    assert r.ok is True


def test_per_order_cap_under_passes():
    r = per_order_cap(parsed_buy(price=30000, qty=0.001), {}, SET)  # 30 USDT
    assert r.ok is True


def test_per_order_cap_over_fails():
    r = per_order_cap(parsed_buy(price=60000, qty=0.002), {}, SET)  # 120 USDT
    assert r.ok is False
    assert "exceeds_per_order_cap" in r.reason


def test_position_cap_buy_within_passes():
    ctx = {"current_price": 60000.0, "base_balance": 0.001}  # 60 USDT existing
    r = position_cap(parsed_buy(price=60000, qty=0.005), ctx, SET)  # adds 300 USDT -> 360 total
    assert r.ok is True


def test_position_cap_buy_over_fails():
    ctx = {"current_price": 60000.0, "base_balance": 0.01}  # 600 USDT existing
    r = position_cap(parsed_buy(price=60000, qty=0.001), ctx, SET)  # +60 = 660 > 500
    assert r.ok is False


def test_position_cap_sell_always_passes():
    ctx = {"current_price": 60000.0, "base_balance": 1.0}  # way over
    r = position_cap(parsed_sell(price=60000, qty=0.5), ctx, SET)
    assert r.ok is True


def test_daily_loss_cap_triggers_when_pnl_below_threshold():
    r = daily_loss_cap(parsed_hold(), {}, SET, pnl_so_far_today_usdt=-31.0)
    assert r.ok is False
    assert "daily_loss" in r.reason


def test_daily_trade_cap_triggers_when_at_limit():
    r = daily_trade_cap(parsed_hold(), {}, SET, trades_today=20)
    assert r.ok is False
    assert "daily_trades" in r.reason


def test_symbol_exclusive_blocks_when_grid_has_open():
    r = symbol_exclusive(
        parsed_buy(), {}, grid_has_open_orders=lambda s: s == "BTCUSDT"
    )
    assert r.ok is False
    assert "grid_open_orders" in r.reason


def test_symbol_exclusive_allows_when_grid_idle():
    r = symbol_exclusive(
        parsed_buy(), {}, grid_has_open_orders=lambda s: False
    )
    assert r.ok is True


def test_run_all_short_circuits_on_first_failure():
    parsed = parsed_buy(price=60000, qty=0.002)  # over per-order cap
    ok, results = run_all(
        parsed, {}, SET, pnl_today=0.0, trades_today=0,
        grid_has_open_orders=lambda s: False,
    )
    assert ok is False
    # schema passed, per_order failed -> only 2 entries returned
    assert len(results) == 2
    assert results[0].ok is True
    assert results[1].ok is False


def test_run_all_all_pass():
    parsed = parsed_buy(price=30000, qty=0.001)  # 30 USDT, fine
    ok, results = run_all(
        parsed, {"current_price": 30000, "base_balance": 0.0}, SET, pnl_today=0.0,
        trades_today=0, grid_has_open_orders=lambda s: False,
    )
    assert ok is True
    assert len(results) == 6