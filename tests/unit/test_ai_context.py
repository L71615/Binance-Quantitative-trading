from app.services.ai_trader.context import gather, summarize_klines


class FakeBroker:
    def get_klines(self, symbol, interval, limit):
        # 5 1h candles rising from 60000 -> 60400
        return [
            [0, "60000", "60100", "59900", "60050", "10"],
            [0, "60050", "60150", "60000", "60100", "12"],
            [0, "60100", "60200", "60080", "60180", "8"],
            [0, "60180", "60300", "60150", "60250", "11"],
            [0, "60250", "60400", "60200", "60380", "15"],
        ]

    def get_account_info(self):
        return {"balances": [
            {"asset": "BTC", "free": "0.005", "locked": "0.001"},
            {"asset": "USDT", "free": "100.00", "locked": "20.00"},
        ]}

    def get_open_orders(self, symbol=None):
        return [{"symbol": "BTCUSDT", "orderId": 1, "side": "BUY", "price": "60000", "origQty": "0.001"}]


def test_summarize_klines_returns_short_string():
    s = summarize_klines([
        [0, "60000", "60100", "59900", "60050", "10"],
        [0, "60050", "60150", "60000", "60100", "12"],
    ])
    assert isinstance(s, str)
    assert "60050" in s or "close" in s.lower()


def test_gather_returns_full_snapshot():
    snap = gather(FakeBroker(), "BTCUSDT", grid_has_open_orders=lambda s: False)
    assert snap["symbol"] == "BTCUSDT"
    assert snap["price"] == 60380.0
    assert "klines_summary" in snap
    assert any(b["asset"] == "BTC" for b in snap["balances"])
    assert snap["open_orders"][0]["orderId"] == 1


def test_gather_uses_kline_close_as_fallback_price():
    class NoClose(FakeBroker):
        def get_klines(self, *a, **k):
            return []

    snap = gather(NoClose(), "BTCUSDT", grid_has_open_orders=lambda s: False)
    assert snap["price"] == 0.0  # no price available


def _broker_obj(**methods):
    """Return a simple object with the listed methods (no self binding)."""
    obj = type("B", (), {})()
    for name, fn in methods.items():
        setattr(obj, name, fn)
    return obj


def test_gather_futures_includes_mark_price_and_position():
    broker = _broker_obj(
        get_klines=lambda symbol, interval, limit: [],
        get_account_info=lambda: {"balances": [], "availableBalance": "1000.0"},
        get_open_orders=lambda symbol=None: [],
        get_mark_price=lambda symbol: {"markPrice": "67238.20"},
        get_position_risk=lambda symbol: [{
            "positionAmt": "0.05",
            "entryPrice": "66500",
            "leverage": "5",
        }],
    )
    out = gather(broker, "BTCUSDT",
                 grid_has_open_orders=lambda s: False,
                 market_type="futures")
    assert out["mark_price"] == 67238.20
    assert out["available_margin_usdt"] == 1000.0
    assert out["current_position_qty"] == 0.05
    assert out["current_position_entry_price"] == 66500.0
    assert out["current_position_leverage"] == 5


def test_gather_futures_no_position():
    broker = _broker_obj(
        get_klines=lambda symbol, interval, limit: [],
        get_account_info=lambda: {"balances": [], "availableBalance": "1000.0"},
        get_open_orders=lambda symbol=None: [],
        get_mark_price=lambda symbol: {"markPrice": "67238.20"},
        get_position_risk=lambda symbol: [],
    )
    out = gather(broker, "BTCUSDT",
                 grid_has_open_orders=lambda s: False,
                 market_type="futures")
    assert out["current_position_qty"] == 0
    assert out["current_position_entry_price"] == 0


def test_gather_spot_excludes_futures_keys():
    snap = gather(FakeBroker(), "BTCUSDT",
                  grid_has_open_orders=lambda s: False,
                  market_type="spot")
    assert "mark_price" not in snap
    assert "available_margin_usdt" not in snap
    assert "current_position_qty" not in snap
