"""Shared transport tests — sign_query, _signed, _request, base url."""
import hashlib
import hmac

import httpx
import pytest

from app.broker._base import _BaseClient, now_ms, sign_query


def test_now_ms_is_unix_milliseconds():
    val = now_ms()
    assert isinstance(val, int)
    assert val > 1_700_000_000_000


def test_sign_query_matches_hmac_sha256():
    params = {"symbol": "BTCUSDT", "side": "BUY"}
    secret = "test_secret"
    expected = hmac.new(
        secret.encode(), "symbol=BTCUSDT&side=BUY".encode(), hashlib.sha256
    ).hexdigest()
    assert sign_query(params, secret) == expected


def test_signed_adds_timestamp_and_signature():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = _BaseClient(
        "api_key", "secret", base_url="https://example.com", http_client=transport
    )
    client._request("GET", "/x", params={"symbol": "BTCUSDT"}, signed=True)
    assert "timestamp" in captured["params"]
    assert "signature" in captured["params"]
    assert captured["params"]["recvWindow"] == "5000"


def test_request_passes_api_key_header():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = _BaseClient(
        "the_api_key", "secret", base_url="https://example.com", http_client=transport
    )
    client._request("GET", "/x")
    assert captured["headers"]["x-mbx-apikey"] == "the_api_key"


def test_unsigned_request_skips_signature():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = _BaseClient(
        "k", "s", base_url="https://example.com", http_client=transport
    )
    client._request("GET", "/x", params={"symbol": "BTCUSDT"})
    assert "signature" not in captured["params"]


def test_close_closes_underlying_http():
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    client = _BaseClient("k", "s", base_url="https://x", http_client=transport)
    client.close()
    # No assertion on internals — just no exception
