"""Binance Spot client. Hand-rolled — does not depend on sammchardy/python-binance.

Signing and HTTP transport live in app/broker/_base.py (shared with the
futures client). Inspiration noted in 借鉴/python-binance/.
"""
from __future__ import annotations

from typing import Any

from app.broker._base import _BaseClient

TESTNET_BASE = "https://testnet.binance.vision"
PROD_BASE = "https://api.binance.com"


class BinanceClient(_BaseClient):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
        http_client=None,
    ):
        super().__init__(
            api_key,
            api_secret,
            base_url=TESTNET_BASE if testnet else PROD_BASE,
            http_client=http_client,
        )

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

# Keep the public signing helpers available from their historical module.
from app.broker._base import now_ms, sign_query  # noqa: E402,F401
