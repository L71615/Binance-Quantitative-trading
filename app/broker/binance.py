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
