"""Shared HTTP transport for spot + futures Binance clients.

Both BinanceClient (spot) and BinanceFuturesClient subclass _BaseClient.
Only the endpoint paths and base URLs differ; signing, headers, and
timeout are identical between the two markets.

Why this module exists: binance.py originally inlined the transport
methods (signing, request building, header injection). When the futures
client was added we needed the same transport — copying it into two
places was the wrong answer. This file is the single source of truth.
"""
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


class _BaseClient:
    """Shared HTTP + signing transport. Subclasses set base_url + paths."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str,
        http_client=None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        import httpx

        if http_client is None:
            self._http = httpx.Client(base_url=base_url, timeout=10.0)
        elif isinstance(http_client, httpx.Client):
            # Already a Client (e.g. existing spot tests wrap a MockTransport
            # in httpx.Client(transport=...) before passing in).
            self._http = http_client
        else:
            # Treat as a transport — lets tests pass httpx.MockTransport(...)
            # directly per the project-wide test convention.
            self._http = httpx.Client(
                base_url=base_url, timeout=10.0, transport=http_client
            )

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
        verb = method.upper()
        if verb == "GET":
            return self._http.get(path, params=q, headers=headers)
        if verb == "DELETE":
            return self._http.delete(path, params=q, headers=headers)
        return self._http.post(path, params=q, headers=headers)

    def close(self) -> None:
        self._http.close()
