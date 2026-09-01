import json
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.ai_decision import AIDecision


def setup_module(_):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


def test_status_endpoint_returns_idle_default(client):
    r = client.get("/api/ai-trader/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "idle"
    assert "max_order_quote_usdt" in data


def test_decisions_endpoint_returns_empty(client):
    r = client.get("/api/ai-trader/decisions")
    assert r.status_code == 200
    assert r.json() == []


def test_decisions_endpoint_returns_rows(client):
    with SessionLocal() as s:
        s.add(AIDecision(
            ts=datetime.now(UTC), symbol="BTCUSDT",
            market_snapshot="{}", prompt="p", raw_response="r",
            parsed=None, action="hold", guard_results="[]",
            outcome="no_trade",
        ))
        s.commit()
    r = client.get("/api/ai-trader/decisions")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "BTCUSDT"


def test_decisions_filter_by_symbol(client):
    with SessionLocal() as s:
        s.add(AIDecision(
            ts=datetime.now(UTC), symbol="ETHUSDT",
            market_snapshot="{}", prompt="p", raw_response="r",
            parsed=None, action="hold", guard_results="[]",
            outcome="no_trade",
        ))
        s.commit()
    r = client.get("/api/ai-trader/decisions?symbol=ETHUSDT")
    rows = r.json()
    assert all(row["symbol"] == "ETHUSDT" for row in rows)


def test_dry_run_returns_parsed_json(client, monkeypatch):
    # Patch the module-level singleton's llm to return canned JSON.
    from app.services.ai_trader import service as svc
    class StubLLM:
        async def chat(self, messages, **kw):
            return json.dumps({"action": "hold", "symbol": "BTCUSDT",
                               "qty": 0, "price": 0,
                               "reason": "dry-run return value"})

    monkeypatch.setattr(svc.trader, "llm", StubLLM())
    monkeypatch.setattr(svc.trader, "broker",
        type("B", (), {
            "get_klines": lambda self, *a, **k: [[0, "60000", "60100",
                                                  "59900", "60050", "10"]],
            "get_account_info": lambda self: {"balances": []},
            "get_open_orders": lambda self, *a, **k: [],
        })())
    r = client.get("/api/ai-trader/dry-run?symbol=BTCUSDT")
    assert r.status_code == 200
    data = r.json()
    assert data["parsed"]["action"] == "hold"
    # Dry-run must return a real guard_verdict now (Finding 2): a list of
    # {ok, reason} entries produced by guards.run_all, NOT None.
    assert isinstance(data["guard_verdict"], list)
    assert len(data["guard_verdict"]) >= 1
    assert all("ok" in r and "reason" in r for r in data["guard_verdict"])
    # No decision row written by this dry-run call: count only rows
    # added after the call so prior tests' seed data don't fail us.
    with SessionLocal() as s:
        from app.models.ai_decision import AIDecision
        baseline = s.query(AIDecision).filter(AIDecision.symbol == "BTCUSDT").count()
    # Re-run dry-run and ensure no NEW rows appear for BTCUSDT.
    r2 = client.get("/api/ai-trader/dry-run?symbol=BTCUSDT")
    assert r2.status_code == 200
    with SessionLocal() as s:
        from app.models.ai_decision import AIDecision
        after = s.query(AIDecision).filter(AIDecision.symbol == "BTCUSDT").count()
    assert after == baseline, f"dry-run wrote a decision row ({baseline}->{after})"


def test_dry_run_never_calls_place_order(client, monkeypatch):
    """Hard rule: dry-run must not place an order, even if the LLM says 'buy'."""
    from app.services.ai_trader import service as svc

    class BuyingLLM:
        async def chat(self, messages, **kw):
            return json.dumps({"action": "buy", "symbol": "BTCUSDT",
                               "qty": 0.001, "price": 30000,
                               "reason": "would-be-real-buy-if-not-dry-run"})

    class BoomOnPlaceBroker:
        def __init__(self):
            self.place_called = False

        def get_klines(self, *a, **k):
            return [[0, "30000", "30100", "29900", "30050", "10"]]

        def get_account_info(self):
            return {"balances": [{"asset": "USDT", "free": "1000"}]}

        def get_open_orders(self, *a, **k):
            return []

        def place_order(self, *a, **kw):
            self.place_called = True
            raise AssertionError("dry-run must NEVER call place_order")

    b = BoomOnPlaceBroker()
    monkeypatch.setattr(svc.trader, "llm", BuyingLLM())
    monkeypatch.setattr(svc.trader, "broker", b)
    r = client.get("/api/ai-trader/dry-run?symbol=BTCUSDT")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["parsed"]["action"] == "buy"
    assert b.place_called is False, "place_order was called during dry-run"


def test_status_endpoint_works_when_no_credentials(client, monkeypatch):
    """Cold-start: no keyring creds, app still boots, status returns sane."""
    # Simulate keyring empty + ensure BinanceClient is NOT constructed.
    import app.api.routers.ai_trader as router_mod
    monkeypatch.setattr(router_mod.trader, "broker", None)
    monkeypatch.setattr(router_mod.trader, "llm", None)
    r = client.get("/api/ai-trader/status")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"


def test_dry_run_503_when_trader_not_wired(client, monkeypatch):
    """If neither llm nor broker is wired, dry-run returns 503."""
    from app.services.ai_trader import service as svc
    monkeypatch.setattr(svc.trader, "llm", None)
    monkeypatch.setattr(svc.trader, "broker", None)
    r = client.get("/api/ai-trader/dry-run?symbol=BTCUSDT")
    assert r.status_code == 503
    assert r.json()["detail"] == "trader_not_wired"


def test_ai_trader_open_through_setup_gate_when_setup_incomplete(client):
    """Spec §7 deliberately puts /api/ai-trader/* outside the first-run
    setup gate so the setup wizard can read AI Trader status.

    Regression-protect this: delete the AppState('setup_completed') row
    (so setup is incomplete), then drive a request through the full
    middleware stack and assert the AI Trader read endpoint is still
    reachable — NOT 403 from the gate.
    """
    from app.models.app_state import AppState
    # Ensure setup is incomplete by deleting the row if it exists.
    with SessionLocal() as s:
        row = s.get(AppState, "setup_completed")
        if row is not None:
            s.delete(row)
            s.commit()
    # Confirm setup gate is actually armed: a gated endpoint returns 403.
    gated = client.get("/api/dashboard/overview")
    assert gated.status_code == 403, (
        "precondition: setup gate must be armed when no AppState row exists"
    )
    # AI Trader read endpoint must be open — must NOT be 403.
    r = client.get("/api/ai-trader/status")
    assert r.status_code == 200, (
        f"AI Trader status blocked by setup gate (got {r.status_code}); "
        "OPEN_PREFIXES in app/main.py must include '/api/ai-trader'"
    )
    assert r.json().get("status") == "idle"
    # And decisions list (no setup state needed) is also reachable.
    r2 = client.get("/api/ai-trader/decisions")
    assert r2.status_code == 200