"""Tests for the 3 futures-specific risk guards + estimate_liq_price."""
import pytest

from app.services.ai_trader.guards import (
    estimate_liq_price,
    leverage_validation,
    liquidation_distance,
    margin_check,
    run_all,
    GuardResult,
)


# ---- estimate_liq_price (pure function) ----

def test_liq_price_long_is_below_entry():
    liq = estimate_liq_price(position_amt=0.1, entry_price=100.0,
                             leverage=5, margin_type="ISOLATED")
    # long 5x: liq ≈ entry * (1 - 1/5) = 80
    assert abs(liq - 80.0) < 1e-6


def test_liq_price_short_is_above_entry():
    liq = estimate_liq_price(position_amt=-0.1, entry_price=100.0,
                             leverage=5, margin_type="ISOLATED")
    # short 5x: liq ≈ entry * (1 + 1/5) = 120
    assert abs(liq - 120.0) < 1e-6


def test_liq_price_zero_position_is_zero():
    assert estimate_liq_price(0.0, 100.0, 5, "ISOLATED") == 0.0


def test_liq_price_invalid_inputs_zero():
    assert estimate_liq_price(0.1, 100.0, 0, "ISOLATED") == 0.0
    assert estimate_liq_price(0.1, 0.0, 5, "ISOLATED") == 0.0


# ---- margin_check ----

def test_margin_check_passes_when_margin_available():
    # buy 0.1 BTC @ 100 = notional 10, leverage 5 → required = 2 USDT
    # available 100, 2 < 80, pass
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    account = {"availableBalance": "100.0"}
    r = margin_check(parsed, {}, settings, broker=None, account_info=account)
    assert r.ok


def test_margin_check_trips_when_margin_insufficient():
    # notional 1000, leverage 5 → required 200 USDT, available 100 → 200 > 80
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 1.0, "price": 1000.0}
    settings = _settings(leverage=5)
    account = {"availableBalance": "100.0"}
    r = margin_check(parsed, {}, settings, broker=None, account_info=account)
    assert not r.ok
    assert "margin_insufficient" in r.reason


def test_margin_check_skips_for_hold():
    parsed = {"action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0}
    settings = _settings(leverage=5)
    account = {"availableBalance": "0.0"}
    r = margin_check(parsed, {}, settings, broker=None, account_info=account)
    assert r.ok


# ---- leverage_validation ----

def test_leverage_validation_calls_set_leverage_when_no_position():
    calls = []
    broker = _broker(
        get_position_risk=lambda sym: [],
        set_leverage=lambda sym, lev: calls.append((sym, lev)) or {"leverage": lev},
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    r = leverage_validation(parsed, {}, settings, broker=broker)
    assert r.ok
    assert calls == [("BTCUSDT", 5)]


def test_leverage_validation_calls_set_leverage_when_mismatch():
    calls = []
    broker = _broker(
        get_position_risk=lambda sym: [{"leverage": 3}],
        set_leverage=lambda sym, lev: calls.append((sym, lev)) or {"leverage": lev},
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    r = leverage_validation(parsed, {}, settings, broker=broker)
    assert r.ok
    assert calls == [("BTCUSDT", 5)]


def test_leverage_validation_skips_set_when_already_matched():
    calls = []
    broker = _broker(
        get_position_risk=lambda sym: [{"leverage": 5}],
        set_leverage=lambda sym, lev: calls.append((sym, lev)) or {"leverage": lev},
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    r = leverage_validation(parsed, {}, settings, broker=broker)
    assert r.ok
    assert calls == []


def test_leverage_validation_trips_on_set_leverage_exception():
    broker = _broker(
        get_position_risk=lambda sym: [],
        set_leverage=lambda sym, lev: (_ for _ in ()).throw(RuntimeError("403 leverage")),
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    r = leverage_validation(parsed, {}, settings, broker=broker)
    assert not r.ok
    assert "leverage_set_failed" in r.reason


# ---- liquidation_distance ----

def test_liquidation_distance_passes_when_no_position():
    broker = _broker(
        get_position_risk=lambda sym: [],
        get_mark_price=lambda sym: {"markPrice": "100.0"},
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 100.0}
    settings = _settings(leverage=5)
    r = liquidation_distance(parsed, {}, settings, broker=broker)
    assert r.ok


def test_liquidation_distance_passes_when_buffer_sufficient():
    broker = _broker(
        get_position_risk=lambda sym: [{
            "positionAmt": "0.1", "entryPrice": "100.0", "leverage": "5"
        }],
        get_mark_price=lambda sym: {"markPrice": "105.0"},
    )
    # long 5x, entry 100, liq ≈ 80, mark 105, distance = |105-80|/105 = 23.8%
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 105.0}
    settings = _settings(leverage=5)
    r = liquidation_distance(parsed, {}, settings, broker=broker)
    assert r.ok


def test_liquidation_distance_trips_when_too_close():
    # long 5x, entry 100, mark 85 → liq 80, distance = |85-80|/85 = 5.88% < 15%
    broker = _broker(
        get_position_risk=lambda sym: [{
            "positionAmt": "0.1", "entryPrice": "100.0", "leverage": "5"
        }],
        get_mark_price=lambda sym: {"markPrice": "85.0"},
    )
    parsed = {"action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 85.0}
    settings = _settings(leverage=5)
    r = liquidation_distance(parsed, {}, settings, broker=broker)
    assert not r.ok
    assert "liquidation_too_close" in r.reason


# ---- run_all market-aware ----

def test_run_all_spot_returns_6_results():
    parsed = {"action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0,
              "reason": "no opportunity"}
    settings = _settings()
    ok, results = run_all(parsed, {}, settings, pnl_today=0.0, trades_today=0,
                          grid_has_open_orders=lambda s: False, market_type="spot")
    assert ok
    assert len(results) == 6


def test_run_all_futures_returns_9_results():
    parsed = {"action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0,
              "reason": "no opportunity"}
    settings = _settings(leverage=5)
    broker = _broker(
        get_position_risk=lambda sym: [],
        set_leverage=lambda sym, lev: {"leverage": lev},
        get_mark_price=lambda sym: {"markPrice": "100.0"},
    )
    account = {"availableBalance": "10000.0"}
    ok, results = run_all(parsed, {}, settings, pnl_today=0.0, trades_today=0,
                          grid_has_open_orders=lambda s: False,
                          market_type="futures", broker=broker, account_info=account)
    assert ok
    assert len(results) == 9


# ---- helpers ----

def _settings(leverage=None):
    """Build a minimal settings-like object. Real settings has 14 fields;
    guards only read .leverage, .margin_type, .max_order_quote_usdt,
    .max_position_per_symbol_usdt, .daily_loss_cap_usdt, .daily_max_trades."""
    s = type("S", (), {})()
    s.leverage = leverage
    s.margin_type = "ISOLATED"
    s.max_order_quote_usdt = 50.0
    s.max_position_per_symbol_usdt = 500.0
    s.daily_loss_cap_usdt = -30.0
    s.daily_max_trades = 20
    return s


def _broker(**methods):
    """Return a simple object with the listed methods (no self binding)."""
    # Avoid descriptor protocol so lambdas receive only the args the guard passes.
    obj = type("B", (), {})()
    for name, fn in methods.items():
        setattr(obj, name, fn)
    return obj
