"""Binance USDⓈ-M Futures client. Sibling of BinanceClient.

Shares transport with the spot client via _BaseClient. Only the endpoint
paths + market-specific methods differ. Signing is identical (HMAC-SHA256
over the canonicalized query string).
"""
from __future__ import annotations

from typing import Any

from app.broker._base import _BaseClient

TESTNET_FUTURES_BASE = "https://testnet.binancefuture.com"
PROD_FUTURES_BASE = "https://fapi.binance.com"


class BinanceFuturesClient(_BaseClient):
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
            base_url=TESTNET_FUTURES_BASE if testnet else PROD_FUTURES_BASE,
            http_client=http_client,
        )

    # ---- 8 interface methods (same shape as BinanceClient) ----

    def get_server_time(self) -> int:
        r = self._request("GET", "/fapi/v1/time")
        r.raise_for_status()
        return r.json()["serverTime"]

    def get_account_info(self) -> dict:
        # v2 account includes availableBalance + positions[]
        r = self._request("GET", "/fapi/v2/account", signed=True)
        r.raise_for_status()
        return r.json()

    def get_symbol_info(self, symbol: str) -> dict:
        r = self._request(
            "GET", "/fapi/v1/exchangeInfo", params={"symbol": symbol}
        )
        r.raise_for_status()
        info = r.json()
        return info["symbols"][0] if info.get("symbols") else {}

    def get_klines(
        self, symbol: str, interval: str, limit: int = 500
    ) -> list[list]:
        r = self._request(
            "GET",
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        r.raise_for_status()
        return r.json()

    def place_order(
        self,
        symbol: str,
        side: str,
        type_: str,
        *,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        position_side: str = "BOTH",
    ) -> dict:
        p: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": type_,
            "quantity": quantity,
            "newOrderRespType": "RESULT",
            "positionSide": position_side,
            "reduceOnly": str(reduce_only).lower(),
        }
        if price is not None:
            p["price"] = price
            p["timeInForce"] = time_in_force
        r = self._request("POST", "/fapi/v1/order", params=p, signed=True)
        r.raise_for_status()
        return r.json()

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        r = self._request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )
        r.raise_for_status()
        return r.json()

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        p = {"symbol": symbol} if symbol else {}
        r = self._request("GET", "/fapi/v1/openOrders", params=p, signed=True)
        r.raise_for_status()
        return r.json()

    def get_all_orders(self, symbol: str, limit: int = 100) -> list[dict]:
        r = self._request(
            "GET",
            "/fapi/v1/allOrders",
            params={"symbol": symbol, "limit": limit},
            signed=True,
        )
        r.raise_for_status()
        return r.json()

    # ---- Futures-only methods (used by guards 7/8/9) ----

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Idempotent on the exchange side — setting to current value is a no-op."""
        r = self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol, "leverage": leverage},
            signed=True,
        )
        r.raise_for_status()
        return r.json()

    def get_position_risk(self, symbol: str | None = None) -> list[dict]:
        """Return one entry per symbol with non-zero position, or empty list."""
        params = {"symbol": symbol} if symbol else {}
        r = self._request(
            "GET", "/fapi/v2/positionRisk", params=params, signed=True
        )
        r.raise_for_status()
        return r.json()

    def get_mark_price(self, symbol: str) -> dict:
        r = self._request(
            "GET", "/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        r.raise_for_status()
        return r.json()
