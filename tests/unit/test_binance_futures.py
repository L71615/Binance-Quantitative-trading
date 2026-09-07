"""BinanceFuturesClient — endpoint contract tests.

Uses httpx.MockTransport to verify the right URL paths + signing kwargs
fire without hitting the network. New endpoints (set_leverage,
get_position_risk, get_mark_price) covered here as futures-only methods.
"""
import httpx
import pytest

from app.broker.futures import (
    BinanceFuturesClient,
    PROD_FUTURES_BASE,
    TESTNET_FUTURES_BASE,
)


def _client(handler):
    transport = httpx.MockTransport(handler)
    return BinanceFuturesClient(
        "api_key", "secret", testnet=False, http_client=transport
    )


def test_testnet_picks_testnet_base():
    c = BinanceFuturesClient("k", "s", testnet=True)
    assert c.base_url == TESTNET_FUTURES_BASE


def test_prod_picks_prod_base():
    c = BinanceFuturesClient("k", "s", testnet=False)
    assert c.base_url == PROD_FUTURES_BASE


def test_get_server_time_hits_fapi_v1_time():
    captured = {}
    def handler(req):
        captured["path"] = req.url.path
        return httpx.Response(200, json={"serverTime": 1700000000000})
    c = _client(handler)
    assert c.get_server_time() == 1700000000000
    assert captured["path"] == "/fapi/v1/time"


def test_get_account_info_is_signed():
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        captured["path"] = req.url.path
        return httpx.Response(200, json={"availableBalance": "100.0"})
    c = _client(handler)
    info = c.get_account_info()
    assert info["availableBalance"] == "100.0"
    assert captured["path"] == "/fapi/v2/account"
    assert "signature" in captured["params"]


def test_get_symbol_info_returns_first_symbol_entry():
    def handler(req):
        return httpx.Response(200, json={
            "symbols": [{
                "symbol": "BTCUSDT",
                "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}],
            }]
        })
    c = _client(handler)
    info = c.get_symbol_info("BTCUSDT")
    assert info["symbol"] == "BTCUSDT"
    assert info["filters"][0]["filterType"] == "LOT_SIZE"


def test_get_klines_calls_fapi_v1_klines():
    captured = {}
    def handler(req):
        captured["path"] = req.url.path
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json=[[1700000000000, "100", "110", "90", "105", "50"]])
    c = _client(handler)
    out = c.get_klines("BTCUSDT", "1h", limit=1)
    assert out[0][4] == "105"
    assert captured["path"] == "/fapi/v1/klines"
    assert captured["params"]["symbol"] == "BTCUSDT"


def test_place_order_default_position_side_is_both():
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"orderId": 1, "status": "NEW"})
    c = _client(handler)
    out = c.place_order("BTCUSDT", "BUY", "LIMIT", quantity=0.01, price=100.0)
    assert out["orderId"] == 1
    assert captured["params"]["positionSide"] == "BOTH"
    assert captured["params"]["reduceOnly"] == "false"


def test_place_order_reduce_only_flag_propagates():
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"orderId": 2})
    c = _client(handler)
    c.place_order("BTCUSDT", "SELL", "LIMIT", quantity=0.01, price=100.0,
                  reduce_only=True)
    assert captured["params"]["reduceOnly"] == "true"


def test_set_leverage_is_signed_post():
    captured = {}
    def handler(req):
        captured["method"] = req.method
        captured["path"] = req.url.path
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"leverage": 5, "maxNotionalValue": "100"})
    c = _client(handler)
    out = c.set_leverage("BTCUSDT", 5)
    assert out["leverage"] == 5
    assert captured["method"] == "POST"
    assert captured["path"] == "/fapi/v1/leverage"
    assert "signature" in captured["params"]


def test_get_position_risk_default_symbol():
    captured = {}
    def handler(req):
        captured["path"] = req.url.path
        return httpx.Response(200, json=[
            {"symbol": "BTCUSDT", "positionAmt": "0.05",
             "entryPrice": "66500", "leverage": "5"}
        ])
    c = _client(handler)
    positions = c.get_position_risk("BTCUSDT")
    assert positions[0]["positionAmt"] == "0.05"
    assert captured["path"] == "/fapi/v2/positionRisk"


def test_get_mark_price_returns_dict():
    def handler(req):
        return httpx.Response(200, json={
            "symbol": "BTCUSDT",
            "markPrice": "67238.20",
            "lastFundingRate": "0.0001",
        })
    c = _client(handler)
    info = c.get_mark_price("BTCUSDT")
    assert info["markPrice"] == "67238.20"
