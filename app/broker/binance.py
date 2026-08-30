"""Binance Spot client. We deliberately do NOT depend on the
sammchardy/python-binance library — we mirror its API patterns but write
our own implementation. Inspiration noted in 借鉴/python-binance/."""
from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def sign_query(params: dict[str, Any], secret: str) -> str:
    qs = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    digest = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


TESTNET_BASE = "https://testnet.binance.vision"
PROD_BASE = "https://api.binance.com"


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True, http_client=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base = TESTNET_BASE if testnet else PROD_BASE
        # http_client is injectable for tests; default to a sync httpx client
        import httpx

        self._http = http_client or httpx.Client(base_url=self.base, timeout=10.0)

    def close(self):
        self._http.close()

    def _signed(self, params: dict[str, Any]) -> dict[str, Any]:
        p = dict(params)
        p.setdefault("timestamp", now_ms())
        p.setdefault("recvWindow", 5000)
        p["signature"] = sign_query(p, self.api_secret)
        return p

    def _request(self, method: str, path: str, *, params=None, signed=False):
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}
        q = params or {}
        if signed:
            q = self._signed(q)
        if method.upper() == "GET":
            return self._http.get(path, params=q, headers=headers)
        return self._http.post(path, params=q, headers=headers)

    def get_server_time(self) -> int:
        r = self._request("GET", "/api/v3/time")
        r.raise_for_status()
        return r.json()["serverTime"]

    def get_account_info(self) -> dict:
        r = self._request("GET", "/api/v3/account", signed=True)
        r.raise_for_status()
        return r.json()

    def get_symbol_info(self, symbol: str) -> dict:
        r = self._request("GET", "/api/v3/exchangeInfo", params={"symbol": symbol})
        r.raise_for_status()
        info = r.json()
        return info["symbols"][0] if info.get("symbols") else {}

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> list[list]:
        r = self._request("GET", "/api/v3/klines", params={
            "symbol": symbol, "interval": interval, "limit": limit,
        })
        r.raise_for_status()
        return r.json()

    def place_order(
        self, symbol: str, side: str, type_: str,
        *, quantity: float, price: float | None = None,
        time_in_force: str = "GTC",
    ) -> dict:
        p: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": type_,
            "quantity": quantity,
            "newOrderRespType": "RESULT",
        }
        if price is not None:
            p["price"] = price
            p["timeInForce"] = time_in_force
        r = self._request("POST", "/api/v3/order", params=p, signed=True)
        r.raise_for_status()
        return r.json()

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        r = self._request("DELETE", "/api/v3/order", params={
            "symbol": symbol, "orderId": order_id,
        }, signed=True)
        r.raise_for_status()
        return r.json()

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        p = {"symbol": symbol} if symbol else {}
        r = self._request("GET", "/api/v3/openOrders", params=p, signed=True)
        r.raise_for_status()
        return r.json()

    def get_all_orders(self, symbol: str, limit: int = 100) -> list[dict]:
        r = self._request("GET", "/api/v3/allOrders", params={
            "symbol": symbol, "limit": limit,
        }, signed=True)
        r.raise_for_status()
        return r.json()
