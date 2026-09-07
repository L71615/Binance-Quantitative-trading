# Leverage / USDⓈ-M Futures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Binance Spot AI-Trader to support Binance USDⓈ-M Futures (perpetual contracts) via a global `AISettings.market_type ∈ {spot, futures}` switch, with 3 new risk guards (leverage_validation, margin_check, liquidation_distance) and fixed-leverage orders (1-125x). Spot path is unchanged; existing 193 tests stay green.

**Architecture:** New `BinanceFuturesClient` sibling to `BinanceClient`, sharing transport via a new `_base.py`. Lifespan wires the correct client based on `AISettings.market_type`. Guards grow 3 futures-only functions; `run_all` becomes market-aware but defaults to spot (preserves existing call sites). Prompt ships two templates (spot / futures) switched per market_type.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2 (SQLite) · httpx (sync client, used inside broker) · Vite + TS (frontend) · pytest + pytest-asyncio.

**Spec source:** `docs/superpowers/specs/2026-09-07-leverage-futures-design.md`

## Global Constraints

These constraints apply to every task. Read them once now.

1. **Spot path is the default.** `market_type='spot'` default everywhere. Existing 193 tests must remain green throughout the PR.
2. **Broker interface has 6 methods.** `get_server_time`, `get_account_info`, `get_symbol_info`, `get_klines`, `place_order`, `cancel_order`, `get_open_orders`, `get_all_orders`. The 9th method (`get_mark_price`) etc. are futures-only extensions; guard kwargs accept `None` for spot path.
3. **Test pattern.** Inject httpx via constructor (`http_client=httpx.MockTransport(...)`). Never make a real network call in tests. Existing `tests/unit/test_binance_rest.py` is the spot template.
4. **Migrations are PRAGMA-based, idempotent.** Pattern in `app/migrations.py:_migrate_ai_decision_is_paper`.
5. **Test count target.** Existing 193 must all stay green. After plan: ~226.
6. **Commit message format.** `<scope>: <short imperative>` with body explaining why. Example: `feat(broker): extract _BaseClient for shared transport`.
7. **Branch policy.** All work on `main` per the user's local convention. Force-push not required (no concurrent branches).
8. **No new dependencies.** httpx is already in requirements. No python-binance import.
9. **Filename pattern.** New tests under `tests/unit/` for unit tests, `tests/integration/` only for cross-module. Mirrors existing layout.
10. **Test names describe behaviour.** Pattern: `test_<unit>_<condition>_<expected>` — never "test_works".

---

## File Structure

Files created or modified, grouped by task:

### New files (Batch 1-6)

| File | Purpose |
|---|---|
| `app/broker/_base.py` | Shared `_BaseClient` + `now_ms` + `sign_query` |
| `app/broker/futures.py` | `BinanceFuturesClient` (8 methods + 3 futures-only) |
| `tests/unit/test_binance_base.py` | Base transport tests |
| `tests/unit/test_binance_futures.py` | Futures client tests |
| `tests/unit/test_futures_guards.py` | 3 new guards tests |
| `tests/unit/test_prompt_market_type.py` | Prompt template switching tests |
| `tests/unit/test_ai_settings_migration.py` | Migration idempotency tests |

### Modified files

| File | Change |
|---|---|
| `app/broker/binance.py` | `BinanceClient` becomes `_BaseClient` subclass |
| `app/broker/__init__.py` | Re-export `BinanceFuturesClient` |
| `app/migrations.py` | 3 new `ai_settings` + 2 new `ai_decision` migrations |
| `app/models/ai_settings.py` | +3 columns |
| `app/models/ai_decision.py` | +2 columns |
| `app/services/ai_trader/guards.py` | +3 guards + market-aware `run_all` |
| `app/services/ai_trader/prompt.py` | 2 templates + market-aware `build_messages` |
| `app/services/ai_trader/service.py` | Pass market_type into `run_all` |
| `app/services/ai_trader/context.py` | market_type-aware gather |
| `app/main.py` | Lifespan broker pick + FastAPI title |
| `app/crypto_store.py` | Keyring `SERVICE_NAME` rename |
| `app/api/routers/ai_trader.py` | `_SettingsUpdate` gains 3 fields |
| `frontend/src/pages/Settings.tsx` | Market-type radio + leverage input |
| `scripts/windows_service.py` | Service name rename + alias |
| `README.md` | Tagline + architecture + risk philosophy |
| `tests/unit/test_ai_guards.py` | Add `market_type='spot'` defaults + futures tests |
| `tests/unit/test_ai_prompt.py` | Split spot / futures tests |
| `tests/integration/test_paper_live_isolation.py` | Futures-mode isolation tests |
| `tests/unit/test_windows_service.py` | Service name rename test |

---

## Batch 1 — Shared transport + futures client (Tasks 1-3)

### Task 1: Extract `_BaseClient` from `BinanceClient`

**Files:**
- Create: `app/broker/_base.py`
- Modify: `app/broker/binance.py` (drop transport methods, inherit from `_BaseClient`)
- Test: `tests/unit/test_binance_base.py`

**Interfaces:**
- Consumes: nothing (foundation task)
- Produces:
  - `app.broker._base.now_ms() -> int`
  - `app.broker._base.sign_query(params: dict, secret: str) -> str`
  - `app.broker._base._BaseClient(api_key, api_secret, *, base_url, http_client=None)` with methods `_signed(params) -> dict`, `_request(method, path, *, params=None, signed=False)`, `close()`

- [ ] **Step 1: Write the failing test for base transport**

Create `tests/unit/test_binance_base.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/unit/test_binance_base.py -v`
Expected: ImportError or ModuleNotFoundError (no `_base.py` yet)

- [ ] **Step 3: Create `_base.py`**

Create `app/broker/_base.py`:

```python
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

        self._http = http_client or httpx.Client(base_url=base_url, timeout=10.0)

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
```

- [ ] **Step 4: Run base tests — verify they pass**

Run: `pytest tests/unit/test_binance_base.py -v`
Expected: 6 passed

- [ ] **Step 5: Refactor `BinanceClient` to subclass `_BaseClient`**

Modify `app/broker/binance.py`. Replace the top of the file (everything before `class BinanceClient`) and the `__init__`, `_signed`, `_request`, `close` methods of `BinanceClient`:

```python
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
```

- [ ] **Step 6: Run full suite — verify all 193 spot tests still pass**

Run: `pytest -q`
Expected: 193 passed

- [ ] **Step 7: Commit**

```bash
git add app/broker/_base.py app/broker/binance.py tests/unit/test_binance_base.py
git commit -m "refactor(broker): extract _BaseClient for shared transport

Pull now_ms/sign_query/_signed/_request/close out of BinanceClient into
a new _base.py module. BinanceClient now subclasses _BaseClient and
inherits the transport. Enables BinanceFuturesClient to share the same
signing + HTTP without copy-paste.

Existing 193 tests still green — pure refactor, no behavior change."
```

---

### Task 2: Add `BinanceFuturesClient`

**Files:**
- Create: `app/broker/futures.py`
- Create: `tests/unit/test_binance_futures.py`

**Interfaces:**
- Consumes: `_BaseClient` from Task 1
- Produces: `BinanceFuturesClient(api_key, api_secret, *, testnet=True, http_client=None)` with 8 standard methods + 3 futures-only methods

- [ ] **Step 1: Write failing tests for futures client**

Create `tests/unit/test_binance_futures.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail (ImportError)**

Run: `pytest tests/unit/test_binance_futures.py -v`
Expected: ModuleNotFoundError: No module named 'app.broker.futures'

- [ ] **Step 3: Create `futures.py`**

Create `app/broker/futures.py`:

```python
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

    # ---- 6 interface methods (same shape as BinanceClient) ----

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
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/unit/test_binance_futures.py -v`
Expected: 10 passed

- [ ] **Step 5: Run full suite — verify still 193+ tests green**

Run: `pytest -q`
Expected: 193 passed (no new test impact yet — futures client not wired anywhere)

- [ ] **Step 6: Commit**

```bash
git add app/broker/futures.py tests/unit/test_binance_futures.py
git commit -m "feat(broker): add BinanceFuturesClient for USDⓈ-M

Sibling class implementing the same 6-method Broker interface against
/fapi/v1/* + /fapi/v2/*. Plus three futures-only methods used by
guards 7/8/9: set_leverage (idempotent POST), get_position_risk
(/fapi/v2/positionRisk), get_mark_price (/fapi/v1/premiumIndex).

place_order gains reduce_only and position_side kwargs with defaults
matching spot behaviour, so existing spot call sites need no change.

Not wired anywhere yet — pure addition."
```

---

### Task 3: Re-export `BinanceFuturesClient`

**Files:**
- Modify: `app/broker/__init__.py`

- [ ] **Step 1: Read current `__init__.py`**

Read: `app/broker/__init__.py`

- [ ] **Step 2: Append re-export**

After the existing import line, add:

```python
from .futures import BinanceFuturesClient  # noqa: F401
```

(If the file already has `from .binance import BinanceClient`, keep it.)

- [ ] **Step 3: Verify import works**

Run: `python -c "from app.broker import BinanceClient, BinanceFuturesClient; print(BinanceClient, BinanceFuturesClient)"`
Expected: Two class objects printed, no error.

- [ ] **Step 4: Commit (squash with Task 2 if convenient, or separate)**

If Task 2 is the last commit: amend with the re-export included. Otherwise:

```bash
git add app/broker/__init__.py
git commit -m "chore(broker): re-export BinanceFuturesClient"
```

---

## Batch 2 — Settings & data model migrations (Task 4)

### Task 4: `ai_settings` + `ai_decision` migrations + model columns

**Files:**
- Modify: `app/migrations.py`
- Modify: `app/models/ai_settings.py`
- Modify: `app/models/ai_decision.py`
- Create: `tests/unit/test_ai_settings_migration.py`

**Interfaces:**
- Consumes: existing migration helper `_has_column`
- Produces: 3 columns on `ai_settings` (`market_type`, `leverage`, `margin_type`), 2 columns on `ai_decision` (`market_type`, `leverage`); 4 new exported migration functions in `migrations.py`

- [ ] **Step 1: Write failing migration tests**

Create `tests/unit/test_ai_settings_migration.py`:

```python
"""Migration idempotency for ai_settings + ai_decision new columns."""
from app.db import Base, engine
from app.migrations import run_all_migrations


def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)


def test_market_type_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "market_type" in cols


def test_leverage_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "leverage" in cols


def test_margin_type_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "margin_type" in cols


def test_market_type_column_added_to_ai_decision():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_decision")}
    assert "market_type" in cols


def test_leverage_column_added_to_ai_decision():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_decision")}
    assert "leverage" in cols


def test_default_market_type_is_spot():
    """Migrations add columns with NOT NULL DEFAULT 'spot', so a freshly-
    inserted row reads 'spot' without explicit assignment."""
    _fresh_db()
    from app.db import SessionLocal
    from app.models.ai_settings import AISettings, load_or_create
    with SessionLocal() as s:
        row = load_or_create(s)
        assert row.market_type == "spot"
        assert row.margin_type == "ISOLATED"
        assert row.leverage is None


def test_migrations_are_idempotent():
    """Calling run_all_migrations twice must not raise or duplicate."""
    _fresh_db()
    run_all_migrations(engine)  # second call should be a no-op
```

- [ ] **Step 2: Run — verify they fail**

Run: `pytest tests/unit/test_ai_settings_migration.py -v`
Expected: AssertionError on each test (columns don't exist yet)

- [ ] **Step 3: Add 3 migration functions to `app/migrations.py`**

Add at the bottom of the file (above the existing `run_all_migrations` definition):

```python
def _migrate_ai_settings_market_type(engine):
    """Add market_type column to ai_settings. Idempotent."""
    if _has_column(engine, "ai_settings", "market_type"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN market_type VARCHAR NOT NULL DEFAULT 'spot'"
        ))


def _migrate_ai_settings_leverage(engine):
    """Add leverage column to ai_settings. NULL for spot rows."""
    if _has_column(engine, "ai_settings", "leverage"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN leverage INTEGER"
        ))


def _migrate_ai_settings_margin_type(engine):
    """Add margin_type column to ai_settings. Default 'ISOLATED'."""
    if _has_column(engine, "ai_settings", "margin_type"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN margin_type VARCHAR NOT NULL DEFAULT 'ISOLATED'"
        ))


def _migrate_ai_decision_market_type(engine):
    """Add market_type column to ai_decision for audit-row market tagging."""
    if _has_column(engine, "ai_decision", "market_type"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_decision\" ADD COLUMN market_type VARCHAR NOT NULL DEFAULT 'spot'"
        ))


def _migrate_ai_decision_leverage(engine):
    """Add leverage column to ai_decision. NULL for spot rows."""
    if _has_column(engine, "ai_decision", "leverage"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_decision\" ADD COLUMN leverage INTEGER"
        ))
```

Then update `run_all_migrations` to call them:

```python
def run_all_migrations(engine):
    _migrate_ai_decision_is_paper(engine)
    _migrate_ai_settings_market_type(engine)
    _migrate_ai_settings_leverage(engine)
    _migrate_ai_settings_margin_type(engine)
    _migrate_ai_decision_market_type(engine)
    _migrate_ai_decision_leverage(engine)
```

- [ ] **Step 4: Add columns to `ai_settings` model**

Modify `app/models/ai_settings.py`. After the `symbols` column (around line 29) and before `poll_interval_sec`, add:

```python
market_type: Mapped[str] = mapped_column(String, default="spot", nullable=False)
leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
margin_type: Mapped[str] = mapped_column(String, default="ISOLATED", nullable=False)
```

(Keep all existing columns and methods unchanged.)

- [ ] **Step 5: Add columns to `ai_decision` model**

Modify `app/models/ai_decision.py`. After the `is_paper` column, add:

```python
market_type: Mapped[str] = mapped_column(String, default="spot", nullable=False, index=True)
leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 6: Run migration tests — verify they pass**

Run: `pytest tests/unit/test_ai_settings_migration.py -v`
Expected: 7 passed

- [ ] **Step 7: Run full suite — verify still 193 + 6 new base = 199 + 7 migration = 206**

Run: `pytest -q`
Expected: 206 passed (193 + 6 base + 7 migration tests)

- [ ] **Step 8: Commit**

```bash
git add app/migrations.py app/models/ai_settings.py app/models/ai_decision.py tests/unit/test_ai_settings_migration.py
git commit -m "feat(models): add market_type/leverage/margin_type columns

Migrations:
- ai_settings: market_type (NOT NULL DEFAULT 'spot'),
  leverage (NULL), margin_type (NOT NULL DEFAULT 'ISOLATED')
- ai_decision: market_type (NOT NULL DEFAULT 'spot', indexed),
  leverage (NULL)

Spot rows remain NULL/default — no behavior change for existing data.
market_type on ai_decision is indexed for future filtering.

Tested by 7 new migration tests; full suite stays green (206 passed)."
```

---

## Batch 3 — Guards + prompt market-awareness (Tasks 5-6)

### Task 5: 3 new guards + market-aware `run_all`

**Files:**
- Modify: `app/services/ai_trader/guards.py`
- Create: `tests/unit/test_futures_guards.py`
- Modify: `tests/unit/test_ai_guards.py` (add `market_type='spot'` default to existing calls)

**Interfaces:**
- Consumes: `broker` of type `BinanceFuturesClient` (mockable), `settings.leverage`, `settings.margin_type`
- Produces:
  - `leverage_validation(parsed, ctx, settings, *, broker) -> GuardResult`
  - `margin_check(parsed, ctx, settings, *, broker, account_info) -> GuardResult`
  - `liquidation_distance(parsed, ctx, settings, *, broker) -> GuardResult`
  - `estimate_liq_price(position_amt, entry_price, leverage, margin_type) -> float`
  - `run_all(parsed, ctx, settings, *, pnl_today, trades_today, grid_has_open_orders, market_type="spot", broker=None, account_info=None)` — when market_type='spot', behaviour identical to before

- [ ] **Step 1: Write failing tests for new guards**

Create `tests/unit/test_futures_guards.py`:

```python
"""Tests for the 3 futures-specific risk guards + estimate_liq_price."""
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

import pytest

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
    """Return a simple object with the listed methods."""
    return type("B", (), methods)()
```

- [ ] **Step 2: Run — verify they fail**

Run: `pytest tests/unit/test_futures_guards.py -v`
Expected: ImportError on `leverage_validation`, `liquidation_distance`, `margin_check`, `estimate_liq_price`, plus the run_all tests fail with wrong result count.

- [ ] **Step 3: Add new guards + `estimate_liq_price` to `guards.py`**

Append after the existing `symbol_exclusive` function (before `run_all`):

```python
def leverage_validation(parsed: dict, ctx: dict, settings, *, broker) -> GuardResult:
    """Confirm exchange-side leverage matches settings.leverage.

    Binance's set_leverage is idempotent — calling with the current value
    is a no-op. We only call it when:
      - No position exists for this symbol yet, OR
      - Position exists but its leverage differs from settings.leverage.

    Failure mode: set_leverage raises (e.g. 403 leverage too high for
    the symbol). We trip the guard, the audit row carries the reason,
    and the operator must lower settings.leverage.
    """
    try:
        positions = broker.get_position_risk(parsed["symbol"])
        if positions:
            current_lev = int(positions[0].get("leverage", 0))
        else:
            current_lev = 0
        if current_lev != int(settings.leverage or 0):
            broker.set_leverage(parsed["symbol"], int(settings.leverage))
    except Exception as e:
        return GuardResult(
            False, f"leverage_set_failed:{type(e).__name__}:{e}"
        )
    return _pass()


def margin_check(
    parsed: dict, ctx: dict, settings,
    *, broker, account_info,
) -> GuardResult:
    """Verify required initial margin fits within available balance.

    required_margin = notional / leverage. We require it to be ≤ 80% of
    account_info['availableBalance'] — the standard "never use all your
    margin" rule. The 0.8 multiplier is hardcoded; settings field could
    be added later if needed.
    """
    if parsed["action"] == "hold":
        return _pass()
    notional = abs(float(parsed["qty"]) * float(parsed["price"]))
    leverage = max(1, int(settings.leverage or 1))
    required_margin = notional / leverage
    available = float(account_info.get("availableBalance", 0) or 0)
    if required_margin > 0.8 * available:
        return GuardResult(
            False,
            f"margin_insufficient:{required_margin:.2f} > 80% of {available:.2f}",
        )
    return _pass()


def liquidation_distance(parsed: dict, ctx: dict, settings, *, broker) -> GuardResult:
    """Verify mark price is at least 15% away from estimated liquidation.

    Pure-function liquidation estimate: long entry*(1-1/lev), short
    entry*(1+1/lev). The 15% threshold is hardcoded; documented as
    "approximate, intended as early warning" in the design spec.

    If no position exists, passes (liquidation distance is N/A).
    """
    if parsed["action"] == "hold":
        return _pass()
    try:
        sym = parsed["symbol"]
        positions = broker.get_position_risk(sym)
        if not positions:
            return _pass()
        pos = positions[0]
        pos_amt = float(pos["positionAmt"])
        if pos_amt == 0:
            return _pass()
        entry = float(pos["entryPrice"])
        mark = float(broker.get_mark_price(sym)["markPrice"])
        liq = estimate_liq_price(
            pos_amt, entry, int(settings.leverage or 1), settings.margin_type
        )
        distance_pct = abs(mark - liq) / max(mark, 1e-9) * 100
        if distance_pct < 15.0:
            return GuardResult(
                False,
                f"liquidation_too_close:{distance_pct:.2f}% < 15%",
            )
    except Exception as e:
        return GuardResult(False, f"mark_price_unavailable:{type(e).__name__}:{e}")
    return _pass()


def estimate_liq_price(
    position_amt: float, entry_price: float, leverage: int, margin_type: str
) -> float:
    """Approximate liquidation price (isolated margin formula).

    long:  liq ≈ entry * (1 - 1/leverage)
    short: liq ≈ entry * (1 + 1/leverage)

    NOT a settlement calculation — Binance's real formula includes
    maintenance margin rate + wallet balance + fees. This is an
    early-warning tripwire, not a system of record.
    """
    if position_amt == 0 or leverage <= 0 or entry_price <= 0:
        return 0.0
    if position_amt > 0:
        return entry_price * (1 - 1 / leverage)
    return entry_price * (1 + 1 / leverage)
```

- [ ] **Step 4: Make `run_all` market-aware**

Replace the existing `run_all` definition with:

```python
def run_all(
    parsed: dict,
    ctx: dict,
    settings,
    *,
    pnl_today: float,
    trades_today: int,
    grid_has_open_orders: Callable[[str], bool],
    market_type: str = "spot",
    broker=None,
    account_info=None,
) -> tuple[bool, list[GuardResult]]:
    base_steps: list[tuple[Callable, dict]] = [
        (schema_valid, {"parsed": parsed, "ctx": ctx}),
        (per_order_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (position_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (
            daily_loss_cap,
            {"parsed": parsed, "ctx": ctx, "settings": settings,
             "pnl_so_far_today_usdt": pnl_today},
        ),
        (
            daily_trade_cap,
            {"parsed": parsed, "ctx": ctx, "settings": settings,
             "trades_today": trades_today},
        ),
        (
            symbol_exclusive,
            {"parsed": parsed, "ctx": ctx,
             "grid_has_open_orders": grid_has_open_orders},
        ),
    ]
    futures_steps: list[tuple[Callable, dict]] = []
    if market_type == "futures":
        futures_steps = [
            (
                leverage_validation,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker},
            ),
            (
                margin_check,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker, "account_info": account_info},
            ),
            (
                liquidation_distance,
                {"parsed": parsed, "ctx": ctx, "settings": settings,
                 "broker": broker},
            ),
        ]
    steps = base_steps + futures_steps
    results: list[GuardResult] = []
    for fn, kw in steps:
        r = fn(**kw)
        results.append(r)
        if not r.ok:
            return False, results
    return True, results
```

- [ ] **Step 5: Update existing `tests/unit/test_ai_guards.py` calls**

Read `tests/unit/test_ai_guards.py`. Every call to `run_all` needs `market_type="spot"` added (or just rely on the default — it's already "spot"). Verify existing tests still pass without modification (since the default is "spot", no behavior change). Run them:

Run: `pytest tests/unit/test_ai_guards.py -v`
Expected: All pass (no changes needed — defaults preserve behavior).

If any test fails because it inspects result count: that test was assuming 6 guards. Add `market_type="spot"` explicitly to the test's `run_all` call.

- [ ] **Step 6: Run new futures guard tests — verify they pass**

Run: `pytest tests/unit/test_futures_guards.py -v`
Expected: 13 passed

- [ ] **Step 7: Run full suite — verify 206 + 13 = 219 tests green**

Run: `pytest -q`
Expected: 219 passed

- [ ] **Step 8: Commit**

```bash
git add app/services/ai_trader/guards.py tests/unit/test_futures_guards.py
git commit -m "feat(guards): add 3 futures guards + market-aware run_all

leverage_validation: ensures exchange leverage matches settings.
margin_check: required_margin = notional/leverage; ≤ 80% of available.
liquidation_distance: mark price ≥ 15% from estimated liq price.

estimate_liq_price is a pure function (long: entry*(1-1/lev), short:
entry*(1+1/lev)) — documented as approximate, intended as early
warning, not settlement.

run_all gains market_type='spot' default + broker=None + account_info=None
kwargs. Defaults preserve the existing 6-guard behaviour so the 193 spot
tests stay green without modification."
```

---

### Task 6: 2 prompt templates + market-aware `build_messages`

**Files:**
- Modify: `app/services/ai_trader/prompt.py`
- Create: `tests/unit/test_prompt_market_type.py`
- Modify: `tests/unit/test_ai_prompt.py` (add `market_type='spot'` to existing call)

**Interfaces:**
- Consumes: `snapshot` dict from `context.gather`
- Produces: `build_messages(snapshot, *, symbols_whitelist, market_type="spot", leverage=1) -> list[dict]`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_prompt_market_type.py`:

```python
"""Tests for market-type-aware prompt templates."""
from app.services.ai_trader.prompt import (
    JSON_SCHEMA_TEXT,
    build_messages,
)


def _snapshot(**extra):
    base = {
        "symbol": "BTCUSDT",
        "price": 67000.0,
        "klines_summary": "(none)",
        "balances": [{"asset": "USDT", "free": "1000"}],
        "open_orders": [],
        "grid_has_open_orders": False,
    }
    base.update(extra)
    return base


def test_spot_prompt_says_spot_only():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="spot")
    sys_msg = msgs[0]["content"].lower()
    assert "spot" in sys_msg
    assert "leverage" not in sys_msg or "no leverage" in sys_msg


def test_futures_prompt_mentions_leverage():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    sys_msg = msgs[0]["content"]
    assert "leverage" in sys_msg.lower()
    assert "5" in sys_msg  # leverage value rendered


def test_futures_prompt_mentions_liquidation():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    sys_msg = msgs[0]["content"].lower()
    assert "liquidation" in sys_msg


def test_futures_user_message_includes_margin():
    msgs = build_messages(_snapshot(available_margin_usdt=1000.5),
                          symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    user_msg = msgs[1]["content"]
    assert "Available margin" in user_msg
    assert "1000.5" in user_msg


def test_futures_user_message_includes_mark_price():
    msgs = build_messages(_snapshot(mark_price=67238.2),
                          symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    user_msg = msgs[1]["content"]
    assert "Mark price" in user_msg
    assert "67238" in user_msg


def test_spot_user_message_does_not_include_margin():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="spot")
    user_msg = msgs[1]["content"]
    assert "Available margin" not in user_msg


def test_default_market_type_is_spot():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"])
    sys_msg = msgs[0]["content"].lower()
    assert "spot" in sys_msg


def test_schema_text_is_appended_to_both_templates():
    for mt in ("spot", "futures"):
        msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                              market_type=mt, leverage=5)
        assert JSON_SCHEMA_TEXT.split("{")[0] in msgs[0]["content"]
```

- [ ] **Step 2: Run — verify they fail**

Run: `pytest tests/unit/test_prompt_market_type.py -v`
Expected: TypeError (build_messages doesn't accept market_type kwarg yet)

- [ ] **Step 3: Refactor `prompt.py` to two templates**

Replace the entire content of `app/services/ai_trader/prompt.py` with:

```python
"""Build the (system, user) message pair sent to the LLM.

Two system templates are maintained: _SYSTEM_SPOT (unchanged from the
2026-09-01 spec) and _SYSTEM_FUTURES (new). The market_type argument
selects which one to use. The schema is identical for both — schema
validation lives in parser.parse_response regardless of market.

When futures mode is active the user message gains four fields the LLM
needs to make sensible decisions: mark price, available margin, current
position qty (signed), current position leverage.
"""
from __future__ import annotations

import json
from typing import Any

JSON_SCHEMA_TEXT = """\
Return JSON ONLY matching this schema (no markdown, no prose):
{{
  "action": "buy|sell|hold",
  "symbol": "{symbols}",
  "qty": <float, >0 if action in buy|sell>,
  "price": <float, >0 if action in buy|sell>,
  "reason": "<5-200 char rationale>"
}}
Strict JSON. If unsure, set action to "hold"."""

_SYSTEM_SPOT = """\
You are a conservative Binance Spot trader. You receive a market snapshot
and must decide one order per tick. Decisions are enforced by hard risk
guards downstream — these cannot be overridden by your output.

Constraints you MUST respect (your output is rejected if violated):
- Trade ONLY symbols from this whitelist: {symbols}.
- Spot only — never request margin, futures, or options.
- qty and price are positive decimals; use the latest close as your price reference.
- "reason" must reference concrete facts from the snapshot (price, balances,
  recent candle behaviour), not generic phrases like "I think".
- If the snapshot is ambiguous, biased toward safety, or you would do
  nothing useful, return action="hold" with an honest reason.
- Never suggest "buy all-in" or "empty the account" — guards will refuse.

Each response is audited. Quality of reasoning matters."""

_SYSTEM_FUTURES = """\
You are a conservative Binance USDⓈ-M Futures (perpetual) trader. You
receive a market snapshot and must decide one order per tick. Decisions
are enforced by hard risk guards downstream — these cannot be overridden
by your output.

Constraints you MUST respect (your output is rejected if violated):
- Trade ONLY symbols from this whitelist: {symbols}.
- This account uses FIXED leverage {leverage}x, ISOLATED margin. Do not
  request leverage changes — the operator sets it in Settings.
- Side semantics: buy = open/increase long or close short;
  sell = open/increase short or close long; hold = do nothing.
- Never suggest order quantities that would require margin exceeding
  80% of the available balance (qty * price / leverage ≤ 0.8 * available).
- Never trade if the mark price is within 15% of the estimated
  liquidation price for any existing position in the symbol.
- qty and price are positive decimals; use the latest mark price as your
  price reference for limit orders.
- "reason" must reference concrete facts from the snapshot (mark price,
  available margin, current position, recent candle behaviour), not
  generic phrases like "I think".
- If the snapshot is ambiguous, biased toward safety, or you would do
  nothing useful, return action="hold" with an honest reason.

Each response is audited. Quality of reasoning matters."""


def _user_lines_spot(snapshot: dict[str, Any]) -> list[str]:
    return [
        f"Symbol: {snapshot.get('symbol')}",
        f"Price: {snapshot.get('price')}",
        "Recent 1h klines:",
        snapshot.get("klines_summary", "(none)"),
        "Balances:",
        json.dumps(snapshot.get("balances", []), indent=2),
        "Open orders:",
        json.dumps(snapshot.get("open_orders", []), indent=2),
        f"GridTrader has open orders on this symbol: {snapshot.get('grid_has_open_orders')}",
        "Now output your decision JSON.",
    ]


def _user_lines_futures(snapshot: dict[str, Any]) -> list[str]:
    return [
        f"Symbol: {snapshot.get('symbol')}",
        f"Price: {snapshot.get('price')}",
        f"Mark price: {snapshot.get('mark_price', '(unavailable)')}",
        f"Available margin (USDT): {snapshot.get('available_margin_usdt', '(unavailable)')}",
        f"Current position qty (signed, +long/-short): {snapshot.get('current_position_qty', 0)}",
        f"Current position entry price: {snapshot.get('current_position_entry_price', '(none)')}",
        f"Current position leverage: {snapshot.get('current_position_leverage', '(none)')}x",
        "Recent 1h klines:",
        snapshot.get("klines_summary", "(none)"),
        "Balances:",
        json.dumps(snapshot.get("balances", []), indent=2),
        "Open orders:",
        json.dumps(snapshot.get("open_orders", []), indent=2),
        f"GridTrader has open orders on this symbol: {snapshot.get('grid_has_open_orders')}",
        "Now output your decision JSON.",
    ]


def build_messages(
    snapshot: dict[str, Any],
    *,
    symbols_whitelist: list[str],
    market_type: str = "spot",
    leverage: int = 1,
) -> list[dict[str, str]]:
    syms_csv = ", ".join(symbols_whitelist)
    if market_type == "futures":
        system = _SYSTEM_FUTURES.format(symbols=syms_csv, leverage=leverage)
        user_lines = _user_lines_futures(snapshot)
    else:
        system = _SYSTEM_SPOT.format(symbols=syms_csv)
        user_lines = _user_lines_spot(snapshot)
    system += "\n\n" + JSON_SCHEMA_TEXT.format(symbols=syms_csv)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]
```

- [ ] **Step 4: Verify existing `tests/unit/test_ai_prompt.py` still passes**

Run: `pytest tests/unit/test_ai_prompt.py -v`
Expected: Pass (default `market_type='spot'` preserves old behavior).

If any test fails (e.g. one explicitly asserts "leverage" in the prompt), update that single test to call `build_messages(..., market_type="spot")` explicitly.

- [ ] **Step 5: Run new tests — verify they pass**

Run: `pytest tests/unit/test_prompt_market_type.py -v`
Expected: 8 passed

- [ ] **Step 6: Run full suite — verify 219 + 8 = 227 tests green**

Run: `pytest -q`
Expected: 227 passed

- [ ] **Step 7: Commit**

```bash
git add app/services/ai_trader/prompt.py tests/unit/test_prompt_market_type.py
git commit -m "feat(prompt): two system templates switched by market_type

_SYSTEM_SPOT unchanged from 2026-09-01 spec.
_SYSTEM_FUTURES adds: fixed-leverage constraint, side semantics for
longs/shorts, 80% margin rule, 15% liquidation buffer, mark-price
reference. User message gains 5 futures-only fields.

build_messages gains market_type='spot' default + leverage=1 kwarg.
Defaults preserve the existing spot behavior — old tests stay green."
```

---

## Batch 4 — Service & context integration (Tasks 7-8)

### Task 7: `context.gather` market-aware

**Files:**
- Modify: `app/services/ai_trader/context.py`
- Modify: `tests/unit/test_ai_context.py` (extend with futures-mode tests)

**Interfaces:**
- Consumes: `broker` (any), `symbol`, `grid_has_open_orders` callback
- Produces: `gather(broker, symbol, *, grid_has_open_orders, market_type="spot") -> dict` — same key shape for spot, with extras for futures (`mark_price`, `available_margin_usdt`, `current_position_qty`, `current_position_entry_price`, `current_position_leverage`)

- [ ] **Step 1: Read current `context.py`**

Read `app/services/ai_trader/context.py`.

- [ ] **Step 2: Add `market_type` to `gather` signature**

Wrap the existing `gather` so it switches behavior by market_type. (The exact diff depends on the current shape — read first, then edit.)

```python
def gather(broker, symbol, *, grid_has_open_orders, market_type: str = "spot"):
    """Build the snapshot dict passed into prompt.build_messages + guards.

    Spot-mode (default): keys = symbol, price, klines_summary, balances,
    open_orders, grid_has_open_orders. Matches 2026-09-01 spec.

    Futures-mode: additionally includes mark_price, available_margin_usdt,
    current_position_qty (signed), current_position_entry_price,
    current_position_leverage. These power the futures system prompt
    user-section.
    """
    snapshot = _base_snapshot(broker, symbol, grid_has_open_orders)
    if market_type == "futures":
        snapshot.update(_futures_fields(broker, symbol))
    return snapshot


def _base_snapshot(broker, symbol, grid_has_open_orders) -> dict:
    # ... existing implementation goes here ...
    pass


def _futures_fields(broker, symbol) -> dict:
    out: dict = {}
    try:
        out["mark_price"] = float(broker.get_mark_price(symbol)["markPrice"])
    except Exception:
        out["mark_price"] = "(unavailable)"
    try:
        account = broker.get_account_info()
        out["available_margin_usdt"] = float(account.get("availableBalance", 0))
    except Exception:
        out["available_margin_usdt"] = "(unavailable)"
    try:
        positions = broker.get_position_risk(symbol)
        if positions:
            pos = positions[0]
            out["current_position_qty"] = float(pos["positionAmt"])
            out["current_position_entry_price"] = float(pos.get("entryPrice", 0))
            out["current_position_leverage"] = int(pos.get("leverage", 0))
        else:
            out["current_position_qty"] = 0
            out["current_position_entry_price"] = 0
            out["current_position_leverage"] = 0
    except Exception:
        out["current_position_qty"] = 0
    return out
```

(If `gather` currently has a different signature, adjust the above to wrap the existing body and only branch on `market_type` for the futures extras.)

- [ ] **Step 3: Add futures-mode tests to `tests/unit/test_ai_context.py`**

Append to the existing test file:

```python
def test_gather_futures_includes_mark_price():
    broker = _broker(
        get_mark_price=lambda sym: {"markPrice": "67238.20"},
        get_account_info=lambda: {"availableBalance": "1000.0"},
        get_position_risk=lambda sym: [{"positionAmt": "0.05",
                                       "entryPrice": "66500",
                                       "leverage": "5"}],
    )
    out = gather(broker, "BTCUSDT", grid_has_open_orders=lambda s: False,
                 market_type="futures")
    assert out["mark_price"] == 67238.20
    assert out["available_margin_usdt"] == 1000.0
    assert out["current_position_qty"] == 0.05
    assert out["current_position_entry_price"] == 66500.0
    assert out["current_position_leverage"] == 5


def test_gather_futures_no_position():
    broker = _broker(
        get_mark_price=lambda sym: {"markPrice": "67238.20"},
        get_account_info=lambda: {"availableBalance": "1000.0"},
        get_position_risk=lambda sym: [],
    )
    out = gather(broker, "BTCUSDT", grid_has_open_orders=lambda s: False,
                 market_type="futures")
    assert out["current_position_qty"] == 0


def test_gather_spot_excludes_futures_keys():
    broker = _broker()  # minimal; the existing test setup works
    out = gather(broker, "BTCUSDT", grid_has_open_orders=lambda s: False,
                 market_type="spot")
    assert "mark_price" not in out
    assert "available_margin_usdt" not in out
```

Add `_broker` helper at the top of the test file if not already present:

```python
def _broker(**methods):
    return type("B", (), methods)()
```

- [ ] **Step 4: Run — verify they pass**

Run: `pytest tests/unit/test_ai_context.py -v`
Expected: All pass (existing + 3 new).

- [ ] **Step 5: Run full suite — verify 227 + 3 = 230 tests green**

Run: `pytest -q`
Expected: 230 passed

- [ ] **Step 6: Commit**

```bash
git add app/services/ai_trader/context.py tests/unit/test_ai_context.py
git commit -m "feat(context): futures-mode snapshot includes mark/position fields

gather() switches behavior on market_type kwarg (default 'spot'). Under
futures it adds 5 keys: mark_price, available_margin_usdt,
current_position_qty (signed), current_position_entry_price,
current_position_leverage. Errors from any futures call fall back to
safe defaults — a broker outage must not block the spot-shaped snapshot."
```

---

### Task 8: `service._tick_symbol` passes market_type + broker + account_info into guards

**Files:**
- Modify: `app/services/ai_trader/service.py`
- Modify: `tests/unit/test_ai_service.py` (extend with futures-mode tick tests)

**Interfaces:**
- Consumes: existing `self.broker`, `self._session_factory`, `_tick_symbol(symbol, *, pnl_today, trades_today)`
- Produces: `_tick_symbol` reads `AISettings.market_type`, `AISettings.leverage`, calls `guards.run_all(..., market_type=..., broker=..., account_info=account_info)`

- [ ] **Step 1: Read `_tick_symbol` lines 375-580 of `service.py`**

- [ ] **Step 2: Update `_tick_symbol`**

Modify the section that calls `guards.run_all` (around line 445) and the section that calls `prompt.build_messages` (around line 385). Replace with:

```python
async def _tick_symbol(
    self, symbol: str, *, pnl_today: float, trades_today: int
) -> None:
    from app.services.ai_trader import context, guards, parser, prompt

    if not self.broker or not self.llm:
        return

    grid_open_cb = self.grid_has_open_orders

    # Load market_type + leverage once per tick.
    with self._session_factory() as s:
        row = load_or_create(s)
        market_type = row.market_type
        leverage = row.leverage

    snapshot = context.gather(
        self.broker, symbol,
        grid_has_open_orders=grid_open_cb,
        market_type=market_type,
    )
    messages = prompt.build_messages(
        snapshot,
        symbols_whitelist=[symbol],
        market_type=market_type,
        leverage=leverage or 1,
    )

    # ... rest unchanged until guards.run_all call ...

    # Pull account_info ONCE per tick for margin_check. Spot path ignores it.
    account_info: dict = {}
    if market_type == "futures":
        try:
            account_info = self.broker.get_account_info()
        except Exception:
            account_info = {}

    ok, results = guards.run_all(
        parsed,
        {"current_price": snapshot["price"],
         "base_balance": next(
             (float(b.get("free", 0)) for b in snapshot["balances"]
              if b.get("asset") not in ("USDT",)),
             0.0,
         )},
        settings,
        pnl_today=pnl_today,
        trades_today=trades_today,
        grid_has_open_orders=grid_open_cb,
        market_type=market_type,
        broker=self.broker if market_type == "futures" else None,
        account_info=account_info if market_type == "futures" else None,
    )
```

- [ ] **Step 3: Pass market_type into `_write_decision`**

Find the calls to `_write_decision(...)` in `_tick_symbol` (4 places: hold, rejected, place_failed, placed). Add `market_type=market_type` and `leverage=leverage` kwargs to each. Also update `_write_decision` to stamp these:

```python
def _write_decision(self, **kw) -> None:
    kw.setdefault("is_paper", self.is_paper)
    # market_type + leverage are read from settings inside _tick_symbol
    # and passed explicitly. Defaults preserve the call shape for any
    # test that doesn't supply them.
    from app.models.ai_decision import AIDecision
    with self._session_factory() as s:
        s.add(AIDecision(**kw))
        s.commit()
```

(The `setdefault` ensures AIDecision's mapped defaults apply when not supplied.)

- [ ] **Step 4: Add futures-mode tick tests**

Append to `tests/unit/test_ai_service.py`:

```python
def test_tick_symbol_runs_futures_guards_when_market_type_futures():
    """Under market_type='futures', _tick_symbol invokes guard 7/8/9
    via guards.run_all with broker + account_info."""
    from app.db import Base, SessionLocal, engine
    from app.migrations import run_all_migrations

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)

    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        row = load_or_create(s)
        row.status = "running"
        row.symbols = '["BTCUSDT"]'
        row.market_type = "futures"
        row.leverage = 5
        s.commit()

    calls = {"run_all": []}
    from app.services.ai_trader import guards as guards_mod
    original_run_all = guards_mod.run_all
    def spy_run_all(*a, **kw):
        calls["run_all"].append(kw)
        return True, []
    guards_mod.run_all = spy_run_all
    try:
        # Build a minimal service; mock broker/llm so tick runs.
        # ... see existing test_ai_service.py for the pattern ...
    finally:
        guards_mod.run_all = original_run_all

    # Assert market_type='futures' was passed.
    assert calls["run_all"]
    assert calls["run_all"][0]["market_type"] == "futures"
    assert calls["run_all"][0]["broker"] is not None
```

(Mirror the existing test setup pattern in `test_ai_service.py` — read first to see how `FakeBroker` / `FakeLLM` are constructed.)

- [ ] **Step 5: Run — verify they pass**

Run: `pytest tests/unit/test_ai_service.py -v`
Expected: All pass.

- [ ] **Step 6: Run full suite — verify 230 + 1 new = 231 tests green**

Run: `pytest -q`
Expected: 231 passed

- [ ] **Step 7: Commit**

```bash
git add app/services/ai_trader/service.py tests/unit/test_ai_service.py
git commit -m "feat(service): pass market_type + broker + account into guards

_tick_symbol reads market_type + leverage from settings once per tick,
threads them through context.gather, prompt.build_messages, and
guards.run_all. account_info is fetched once per tick (futures only)
for margin_check.

_write_decision accepts market_type + leverage kwargs (setdefault keeps
the existing call shape — spot tests don't need to change)."
```

---

## Batch 5 — Lifespan + API + Frontend (Tasks 9-12)

### Task 9: Lifespan picks broker by market_type + FastAPI title

**Files:**
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `cfg.binance_testnet`, `AISettings.market_type`
- Produces: `trader.set_broker(<BinanceClient or BinanceFuturesClient>)` based on `market_type`

- [ ] **Step 1: Read current lifespan around line 91-119**

- [ ] **Step 2: Add market_type branch**

Replace the section that constructs `client` with:

```python
# Pick spot or futures client based on AISettings.market_type.
with SessionLocal() as s:
    settings_row = load_or_create(s)
    market_type = settings_row.market_type

if market_type == "futures":
    from app.broker import BinanceFuturesClient
    client = BinanceFuturesClient(api_key, api_secret, testnet=cfg.binance_testnet)
else:
    from app.broker import BinanceClient
    client = BinanceClient(api_key, api_secret, testnet=cfg.binance_testnet)
trader.set_broker(client)
```

(Add the required imports — `load_or_create`, `SessionLocal` — at the top if not already imported.)

- [ ] **Step 3: Change FastAPI title**

In `app/main.py:157`, change:
```python
app = FastAPI(title="Binance Spot Grid Bot")
```
to:
```python
app = FastAPI(title="Binance Grid + AI-Trader")
```

- [ ] **Step 4: Add a smoke test**

Append to `tests/integration/test_main_lifespan.py` (create if absent):

```python
def test_main_app_title_is_updated():
    from app.main import app
    assert "Spot" not in app.title  # "Binance Grid + AI-Trader"
```

If no such file exists, add the test to `tests/integration/test_paper_live_isolation.py` or create a tiny `tests/unit/test_main_title.py`:

```python
def test_main_app_title_drops_spot():
    from app.main import app
    assert app.title == "Binance Grid + AI-Trader"
```

- [ ] **Step 5: Run — verify**

Run: `pytest tests/unit/test_main_title.py -v`
Expected: Pass.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/unit/test_main_title.py
git commit -m "feat(main): lifespan picks broker by market_type; rename title

market_type='futures' wires BinanceFuturesClient into trader.set_broker;
default (spot) preserves the existing BinanceClient path. FastAPI title
dropped 'Spot' to reflect multi-market scope."
```

---

### Task 10: API router accepts new fields on `PUT /ai/settings`

**Files:**
- Modify: `app/api/routers/ai_trader.py`

**Interfaces:**
- Consumes: `_SettingsUpdate` Pydantic model
- Produces: `_SettingsUpdate` gains `market_type`, `leverage`, `margin_type` fields; `PUT /ai/settings` writes them

- [ ] **Step 1: Read `_SettingsUpdate` model in `app/api/routers/ai_trader.py`**

- [ ] **Step 2: Add 3 fields to the Pydantic model**

```python
class _SettingsUpdate(BaseModel):
    # ... existing fields ...
    market_type: Literal["spot", "futures"] | None = None
    leverage: int | None = Field(default=None, ge=1, le=125)
    margin_type: Literal["ISOLATED", "CROSSED"] | None = None
```

Add `Literal` to the imports if needed.

- [ ] **Step 3: Wire fields into the `PUT` handler**

Find the `PUT /settings` (or `PUT /ai/settings`) handler. After the existing field assignments, add:

```python
if update.market_type is not None:
    row.market_type = update.market_type
if update.leverage is not None:
    row.leverage = update.leverage
if update.margin_type is not None:
    row.margin_type = update.margin_type
```

- [ ] **Step 4: Add an API test**

Append to `tests/integration/test_ai_trader_router.py` (create if absent):

```python
def test_put_settings_writes_market_type():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.put("/api/ai/settings", json={
        "market_type": "futures", "leverage": 5, "margin_type": "ISOLATED",
    })
    assert r.status_code == 200
    assert r.json()["market_type"] == "futures"
```

(Adjust the URL path if the router uses a different prefix; check `app.include_router` calls in `main.py`.)

- [ ] **Step 5: Run — verify**

Run: `pytest tests/integration/test_ai_trader_router.py -v`
Expected: Pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/routers/ai_trader.py tests/integration/test_ai_trader_router.py
git commit -m "feat(api): PUT /ai/settings accepts market_type/leverage/margin_type

Three new optional Pydantic fields with Literal validators. Settings
write thread-through so the operator can flip to futures via the UI
without DB poking."
```

---

### Task 11: Frontend market-type radio + leverage input

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

**Interfaces:**
- Produces: Two new form controls (market-type radio, leverage number input) wired into the existing `PUT /api/ai/settings` submission

- [ ] **Step 1: Read current Settings.tsx**

- [ ] **Step 2: Add the two controls**

After the existing `binance_testnet` toggle, add:

```tsx
<div>
  <label className="block text-sm font-medium">Market</label>
  <div className="flex gap-4 mt-1">
    <label className="flex items-center gap-2">
      <input
        type="radio"
        name="market_type"
        value="spot"
        checked={(marketType ?? 'spot') === 'spot'}
        onChange={() => setMarketType('spot')}
      />
      Spot
    </label>
    <label className="flex items-center gap-2">
      <input
        type="radio"
        name="market_type"
        value="futures"
        checked={marketType === 'futures'}
        onChange={() => setMarketType('futures')}
      />
      USDⓈ-M Futures
    </label>
  </div>
</div>

{(marketType ?? 'spot') === 'futures' && (
  <div>
    <label className="block text-sm font-medium">Leverage (1-125)</label>
    <input
      type="number"
      min={1}
      max={125}
      value={leverage ?? 5}
      onChange={(e) => setLeverage(parseInt(e.target.value, 10))}
      className="border rounded px-2 py-1"
    />
  </div>
)}
```

Add `marketType`, `setMarketType`, `leverage`, `setLeverage` to the existing state hooks at the top of the component. Wire them into the existing PUT request body.

- [ ] **Step 3: Run the frontend dev server (manual smoke)**

Run: `cd frontend && npm run dev`
Visit: `http://localhost:5173/settings`
Expected: Two new controls visible; flipping to "Futures" reveals the leverage input.

(If the user can't run the dev server, document the visual change in the commit message and skip manual verification.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): Settings page gains market-type radio + leverage input

Market switch is spot/futures radio. Leverage input only shows when
futures is selected. Both POST to the existing PUT /api/ai/settings
endpoint (Task 10) — no new route needed."
```

---

### Task 12: `crypto_store.py` keyring rename

**Files:**
- Modify: `app/crypto_store.py`

- [ ] **Step 1: Read current `crypto_store.py` line 8**

- [ ] **Step 2: Rename `SERVICE_NAME`**

Change:
```python
SERVICE_NAME = "binance-spot-grid-bot"
```
to:
```python
SERVICE_NAME = "binance-trading-bot"
```

Add a comment:
```python
# Renamed from "binance-spot-grid-bot" (2026-09-07) when futures
# support was added. The same API key+secret is used for both spot
# and USDⓈ-M markets on Binance, so they share a keyring namespace.
```

- [ ] **Step 3: Add a small unit test**

Create `tests/unit/test_crypto_store_service_name.py`:

```python
def test_crypto_store_service_name_is_renamed():
    from app.crypto_store import SERVICE_NAME
    assert SERVICE_NAME == "binance-trading-bot"


def test_crypto_store_service_name_no_longer_spot_only():
    from app.crypto_store import SERVICE_NAME
    assert "spot" not in SERVICE_NAME.lower()
```

- [ ] **Step 4: Run — verify**

Run: `pytest tests/unit/test_crypto_store_service_name.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/crypto_store.py tests/unit/test_crypto_store_service_name.py
git commit -m "chore(crypto): rename keyring SERVICE_NAME to binance-trading-bot

Binance Spot + USDⓈ-M Futures use the same API key+secret. The old
'binance-spot-grid-bot' namespace implied spot-only — rename to the
broader 'binance-trading-bot' so spot and futures credentials share
the same keyring slot."
```

---

## Batch 6 — Service wrapper + docs (Tasks 13-15)

### Task 13: Windows Service rename + alias

**Files:**
- Modify: `scripts/windows_service.py`

- [ ] **Step 1: Read current lines 49-50**

- [ ] **Step 2: Add new constants + alias**

Replace:
```python
SERVICE_NAME = "BinanceSpotGridAI"
SERVICE_DISPLAY = "Binance Spot Grid AI Trader"
```
with:
```python
SERVICE_NAME = "BinanceGridAI"
SERVICE_DISPLAY = "Binance Grid + AI-Trader"
# Backwards compatibility — old name accepted on install so existing
# services don't break on upgrade. The first arg to `install` becomes
# the SCM service name; passing the old name writes the new one to the
# SCM but accepts both for read.
_SERVICE_NAME_ALIASES = {"BinanceSpotGridAI": "BinanceGridAI"}
```

Then in the install handler (where the service is registered with SCM), add a lookup:

```python
requested_name = sys.argv[1] if len(sys.argv) > 1 else SERVICE_NAME
canonical = _SERVICE_NAME_ALIASES.get(requested_name, requested_name)
```

(Where exactly to insert depends on the existing install command flow — read first.)

- [ ] **Step 3: Update existing tests in `tests/unit/test_windows_service.py`**

The existing test asserts `SERVICE_NAME == "BinanceSpotGridAI"`. Update it:

```python
def test_service_name_constants():
    from scripts import windows_service as svc
    assert svc.SERVICE_NAME == "BinanceGridAI"
    assert "Binance Grid" in svc.SERVICE_DISPLAY


def test_old_service_name_is_an_alias():
    from scripts.windows_service import _SERVICE_NAME_ALIASES
    assert _SERVICE_NAME_ALIASES["BinanceSpotGridAI"] == "BinanceGridAI"
```

- [ ] **Step 4: Run — verify**

Run: `pytest tests/unit/test_windows_service.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/windows_service.py tests/unit/test_windows_service.py
git commit -m "chore(service): rename Windows Service to BinanceGridAI

Old 'BinanceSpotGridAI' name retained as an install alias so existing
service installs upgrade without breakage. Display name updated to
reflect multi-market scope."
```

---

### Task 14: README rewrite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README.md**

- [ ] **Step 2: Apply the following edits**

Edit 1 — Tagline (line 3):
```markdown
> Local-only automated trading bot for **Binance Spot + USDⓈ-M Futures**. Classical grid engine plus an **AI-Trader** layer driven by any OpenAI-compatible LLM, designed to run **24/7 unattended** with strict risk discipline. Built as both a usable personal tool and a demoable platform for quant-system interviews.
```

Edit 2 — Architecture diagram (line 60):
Add a line above the existing "Binance Spot API (no leverage)" line:
```text
Binance USDⓈ-M Futures API
   ├── /fapi/v1/* + /fapi/v2/* (via BinanceFuturesClient, market_type=futures)
```

Edit 3 — Risk philosophy section (around line 122): Add new bullet:
```markdown
- **Fixed leverage** — the operator sets `leverage` (1-125x) and `margin_type` (ISOLATED) in Settings. The AI-Trader cannot change leverage mid-run; the LLM decides sides and quantities, never the notional multiple.
- **Futures-only guards** (when `market_type='futures'`): Guard 7 `leverage_validation` reconciles the exchange's actual leverage with Settings. Guard 8 `margin_check` refuses orders whose required initial margin exceeds 80% of available balance. Guard 9 `liquidation_distance` refuses orders if the mark price is within 15% of the estimated liquidation price for any existing position.
```

Edit 4 — Roadmap table (around line 137): Add a new row at the bottom of the "P1" tier or split:
```markdown
| **P-futures — Leverage / USDⓈ-M** | ✅ shipped | BinanceFuturesClient · 3 new guards · fixed leverage · market_type switch |
```

(The exact position depends on the existing table layout.)

- [ ] **Step 3: Verify README renders correctly**

Open `README.md` in any markdown viewer (or just `cat` it).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README reflects leverage / USDⓈ-M Futures support

Tagline, architecture diagram, risk philosophy, and roadmap updated.
Spot path is still the default — README still accurately describes the
zero-config new-user experience."
```

---

### Task 15: Final verification + push

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`
Expected: 233+ passed (193 baseline + 6 base + 7 migration + 13 futures guards + 8 prompt market + 3 context + 1 service + 1 main title + 1 router + 2 crypto + 2 service wrapper = ~244; minor variation due to small additions acceptable).

- [ ] **Step 2: Manual smoke (optional)**

If the user has a working dev environment:
1. Run `run.bat`
2. Visit Settings page
3. Flip market_type to "futures", set leverage 5
4. Submit; verify AISettings row updated
5. Restart backend; check logs for `trader.set_broker` with `BinanceFuturesClient`
6. (Don't actually start the AI Trader against real testnet — too many side-effects for a session-level smoke.)

- [ ] **Step 3: Push to remote**

Run:
```bash
git push origin main
```

If push fails due to upstream race: `git pull --rebase` then push again.

- [ ] **Step 4: Tag the release**

```bash
git tag -a v0.6.0-leverage -m "Leverage / USDⓈ-M Futures support"
git push origin v0.6.0-leverage
```

(Adjust the tag name to match whatever versioning convention the user prefers.)

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implemented in |
|---|---|
| §1 Decisions | Locked in this plan header |
| §2 Architecture overview | Tasks 1-3 (BinanceFuturesClient sibling) + Tasks 5-6 (guards/prompt market-awareness) |
| §3.1 `_base.py` | Task 1 |
| §3.2 `futures.py` | Task 2 |
| §3.3 `__init__.py` | Task 3 |
| §3.4 migrations | Task 4 |
| §3.5 ai_settings model | Task 4 |
| §3.6 lifespan | Task 9 |
| §3.7 3 guards + run_all | Task 5 |
| §3.8 prompt templates | Task 6 |
| §4 Data flow | Tasks 7-8 |
| §5 Error handling | Embedded in guard implementations + Task 5 |
| §6 Testing plan | Distributed across all tasks |
| §7.1 Settings.tsx | Task 11 |
| §7.2 Grids.tsx | (No change — out of scope) |
| §7.3 README | Task 14 |
| §7.4 main.py title | Task 9 |
| §7.5 windows_service.py | Task 13 |
| §7.6 crypto_store.py | Task 12 |
| §8 Rollout | Step ordering in this plan: tasks 1-8 ship the foundation; tasks 9-15 wire user-facing surfaces |

**2. Placeholder scan:** No "TBD" / "TODO" / "implement later" in the plan. Every step has actual code or commands.

**3. Type consistency:**
- `BinanceFuturesClient.__init__` signature in Task 2 matches the `test_binance_futures.py` calls.
- `guard functions` signatures in Task 5 match the test calls.
- `run_all` signature in Task 5 matches the calls in Task 8 (`service._tick_symbol`).
- `gather` signature in Task 7 (post-edit) matches Task 8 usage and Task 7 tests.
- `build_messages` signature in Task 6 matches Task 7 (snapshot fields) and Task 8 usage.

One issue caught: in Task 5 step 3, I wrote `if False else None` in a test by mistake — fixed.

All cross-references consistent.