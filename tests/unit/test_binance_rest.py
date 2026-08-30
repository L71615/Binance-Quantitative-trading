import httpx
import pytest

from app.broker.binance import BinanceClient


def _make_client(handler) -> BinanceClient:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://testnet.binance.vision", transport=transport)
    return BinanceClient("k", "s", testnet=True, http_client=client)


def test_get_account_info(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/account":
            return httpx.Response(200, json={"makerCommission": 10, "balances": []})
        return httpx.Response(404)

    c = _make_client(handler)
    info = c.get_account_info()
    assert info["makerCommission"] == 10
    c.close()


def test_get_klines(monkeypatch):
    sample = [
        [1700000000000, "100.0", "110.0", "95.0", "105.0", "12.34",
         1700003600000, "1295.7", 100, "6.17", "647.85", "0"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/klines":
            qs = dict(request.url.params)
            assert qs["symbol"] == "BTCUSDT"
            assert qs["interval"] == "1h"
            return httpx.Response(200, json=sample)
        return httpx.Response(404)

    c = _make_client(handler)
    rows = c.get_klines("BTCUSDT", "1h", limit=1)
    assert len(rows) == 1
    assert rows[0][1] == "100.0"
    c.close()


def test_place_order_sends_signed_request(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"orderId": 1, "status": "NEW"})

    c = _make_client(handler)
    r = c.place_order(
        "BTCUSDT", "BUY", "LIMIT", quantity=0.001, price=30000.0
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v3/order"
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["side"] == "BUY"
    assert captured["params"]["type"] == "LIMIT"
    assert captured["params"]["signature"]  # present
    assert r["status"] == "NEW"
    c.close()


def test_cancel_order_sends_delete_request(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"orderId": 1, "status": "CANCELED"})

    c = _make_client(handler)
    r = c.cancel_order("BTCUSDT", 1)
    assert captured["method"] == "DELETE"
    assert captured["path"] == "/api/v3/order"
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["orderId"] == "1"
    assert captured["params"]["signature"]  # present
    assert r["status"] == "CANCELED"
    c.close()
