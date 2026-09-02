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


# -- Task 11 fix pass 3: the lifespan must wire BOTH clients ---------------
#
# These tests drive the REAL app lifespan (via `with TestClient(app)`), which
# is the production wiring path. Every pre-existing test monkeypatches
# `trader.llm` directly, so the production path was entirely untested — that
# is how "the lifespan never calls set_llm" survived three commits.
#
# Credentials are injected by monkeypatching `load_secret`, so NOTHING is
# written to the keyring and no real key appears anywhere. The placeholder
# base_url uses the reserved `.invalid` TLD, which cannot resolve, so even an
# accidental request could not reach a real endpoint. No test here makes a
# network call: BinanceClient builds an httpx.Client but issues no request,
# and LLMClient builds no client at all (httpx.AsyncClient is created
# per-call inside .chat(), which we never invoke).

_FAKE_BINANCE_KEY = "fake-binance-key-for-tests"
_FAKE_BINANCE_SECRET = "fake-binance-secret-for-tests"
_FAKE_LLM_KEY = "fake-llm-key-for-tests"
_FAKE_LLM_BASE_URL = "https://llm.invalid/v1"


@pytest.fixture
def wiring_env(monkeypatch):
    """Isolate the singleton + neutralise ambient LLM env for wiring tests.

    Pinning trader.broker/llm through monkeypatch means whatever the lifespan
    assigns is rolled back at teardown, so these tests cannot leak a wired
    singleton into the rest of the suite. Deleting the LLM_* env vars (and
    clearing the settings cache) makes the "absent credentials" cases
    deterministic instead of dependent on the developer's shell.
    """
    from app.config import get_settings
    from app.services.ai_trader import service as svc

    monkeypatch.setattr(svc.trader, "broker", None)
    monkeypatch.setattr(svc.trader, "llm", None)
    for var in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield svc.trader
    # Close the httpx client if a real BinanceClient got wired, then drop the
    # settings cache so no test-only env leaks into later tests.
    broker = getattr(svc.trader, "broker", None)
    if broker is not None and hasattr(broker, "close"):
        try:
            broker.close()
        except Exception:
            pass
    get_settings.cache_clear()


def _fake_load_secret(*, binance: bool, llm: bool):
    """Build a load_secret stub for a given credential combination."""
    values = {}
    if binance:
        values["api_key"] = _FAKE_BINANCE_KEY
        values["api_secret"] = _FAKE_BINANCE_SECRET
    if llm:
        values["llm_api_key"] = _FAKE_LLM_KEY
        values["llm_base_url"] = _FAKE_LLM_BASE_URL
        values["llm_model"] = "test-model"
    return lambda slug: values.get(slug)


def test_lifespan_wires_llm_and_broker_when_both_credentials_present(
    monkeypatch, wiring_env
):
    """The realistic production case: both Binance and LLM credentials are
    configured, so the lifespan must wire BOTH clients and /status must
    report wiring_ok=True.

    This case was previously IMPOSSIBLE: the lifespan only ever called
    set_broker, so trader.llm stayed None forever and wiring_ok could never
    be True in production. No existing test would have noticed.
    """
    from app.services.llm import LLMClient

    monkeypatch.setattr(
        "app.crypto_store.load_secret", _fake_load_secret(binance=True, llm=True)
    )
    with TestClient(app) as c:
        trader = wiring_env
        assert trader.broker is not None, "lifespan did not wire the broker"
        assert trader.llm is not None, (
            "lifespan did not wire the LLM — trader.llm is still None, so the "
            "tick loop can never reach an LLM and /dry-run returns 503 forever"
        )
        # It must be the real client, configured from the injected creds.
        assert isinstance(trader.llm, LLMClient)
        assert trader.llm.is_configured() is True
        assert trader.llm.base_url == _FAKE_LLM_BASE_URL
        assert trader.llm.model == "test-model"

        r = c.get("/api/ai-trader/status")
        assert r.status_code == 200
        data = r.json()
        assert data["broker_wired"] is True
        assert data["llm_wired"] is True
        assert data["wiring_ok"] is True, (
            "wiring_ok must be True when both Binance and LLM credentials "
            f"are configured; got {data!r}"
        )
        # /dry-run's guard is `not trader.llm or not trader.broker`. Assert
        # that condition is now False rather than calling the endpoint —
        # invoking it would make a REAL network call to the LLM.
        assert not (not trader.llm or not trader.broker), (
            "dry-run would still return 503 in production"
        )


def test_lifespan_cold_start_with_no_credentials_still_boots(
    monkeypatch, wiring_env
):
    """Hard constraint: no Binance creds and no LLM creds (this machine's
    actual state) must still boot, and /status must respond wiring_ok=False."""
    monkeypatch.setattr(
        "app.crypto_store.load_secret", _fake_load_secret(binance=False, llm=False)
    )
    with TestClient(app) as c:
        trader = wiring_env
        assert trader.broker is None
        assert trader.llm is None
        r = c.get("/api/ai-trader/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "idle"
        assert data["broker_wired"] is False
        assert data["llm_wired"] is False
        assert data["wiring_ok"] is False
        # And dry-run degrades to a clean 503 rather than crashing.
        assert c.get("/api/ai-trader/dry-run?symbol=BTCUSDT").status_code == 503


@pytest.mark.parametrize(
    "binance,llm",
    [(True, False), (False, True)],
    ids=["binance_only", "llm_only"],
)
def test_lifespan_partial_credentials_leave_wiring_ok_false(
    monkeypatch, wiring_env, binance, llm
):
    """Half-configured is not configured: exactly one client wired means
    wiring_ok=False, and the per-client flags still report the truth."""
    monkeypatch.setattr(
        "app.crypto_store.load_secret", _fake_load_secret(binance=binance, llm=llm)
    )
    with TestClient(app) as c:
        trader = wiring_env
        assert (trader.broker is not None) is binance
        assert (trader.llm is not None) is llm
        data = c.get("/api/ai-trader/status").json()
        assert data["broker_wired"] is binance
        assert data["llm_wired"] is llm
        assert data["wiring_ok"] is False
        assert data["wiring_ok"] == (data["broker_wired"] and data["llm_wired"])


def test_lifespan_malformed_settings_leaves_status_responding_unwired(
    monkeypatch, wiring_env
):
    """The narrowed `except (pydantic.ValidationError,)` path.

    `wiring_ok` is now a derived read-only property, so the handler can no
    longer assign `_ai_trader.wiring_ok = False` (that would raise
    AttributeError). It clears both clients instead — which is both honest
    and stronger, since it also prevents a half-wired singleton from being
    used. Assert the app still boots and /status reports not-wired.
    """
    import pydantic

    def _boom():
        raise pydantic.ValidationError.from_exception_data("Settings", [])

    # Binance creds present, so without the raise the broker WOULD be wired;
    # this proves the handler actively clears a partially-wired singleton.
    monkeypatch.setattr(
        "app.crypto_store.load_secret", _fake_load_secret(binance=True, llm=True)
    )
    monkeypatch.setattr("app.config.get_settings", _boom)
    with TestClient(app) as c:
        trader = wiring_env
        assert trader.broker is None, "handler must clear a half-wired broker"
        assert trader.llm is None
        r = c.get("/api/ai-trader/status")
        assert r.status_code == 200
        data = r.json()
        assert data["wiring_ok"] is False
        assert data["broker_wired"] is False
        assert data["llm_wired"] is False


# -- Task 12: control endpoints (start / pause / resume / emergency-stop / reset) + live-arming gate

# Testnet-mode helper: the brief's two live-arming tests force live mode by
# monkeypatching _is_live_mode in the service module. Every other Task 12
# test pins _is_live_mode to False so they exercise testnet codepaths and
# don't trip the arming gate accidentally.
import app.services.ai_trader.service as _svc  # noqa: E402


@pytest.fixture
def _testnet_mode(monkeypatch):
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: False)


def test_start_and_pause_round_trip(client, _testnet_mode):
    assert client.post("/api/ai-trader/start").status_code == 200
    r = client.post("/api/ai-trader/pause")
    assert r.status_code == 200
    r = client.get("/api/ai-trader/status")
    assert r.json()["status"] == "paused"


def test_resume_from_paused(client, _testnet_mode):
    assert client.post("/api/ai-trader/start").status_code == 200
    assert client.post("/api/ai-trader/pause").status_code == 200
    assert client.post("/api/ai-trader/resume").status_code == 200
    assert client.get("/api/ai-trader/status").json()["status"] == "running"


def test_emergency_stop_lands_on_stopped(client, _testnet_mode):
    assert client.post("/api/ai-trader/start").status_code == 200
    assert client.post("/api/ai-trader/emergency-stop").status_code == 200
    assert client.get("/api/ai-trader/status").json()["status"] == "stopped"


def test_reset_returns_to_idle(client, _testnet_mode):
    assert client.post("/api/ai-trader/start").status_code == 200
    assert client.post("/api/ai-trader/emergency-stop").status_code == 200
    r = client.post("/api/ai-trader/reset")
    assert r.status_code == 200
    assert client.get("/api/ai-trader/status").json()["status"] == "idle"


def test_reset_without_stopped_or_error_is_409(client, _testnet_mode):
    """reset() only accepts status ∈ {stopped, error}. From idle (the default
    after setup_module) it must refuse with 409 not_stopped."""
    r = client.post("/api/ai-trader/reset")
    assert r.status_code == 409
    assert r.json()["detail"] == "not_stopped"


def test_reset_from_error_returns_to_idle(client, _testnet_mode):
    """Task 10's tripwires can land the service in `error` after 5
    consecutive LLM failures. Spec §3 says reset() must recover from error
    as well as stopped; without this path error is unrecoverable except
    by hand-editing the DB. Use the service API to enter error directly
    (faster + deterministic than driving 5 ticks), then reset through the
    HTTP surface."""
    # Drive service into error via the low-level setter used by tripwires.
    from app.services.ai_trader.service import trader as _trader
    _trader._set_status("error", reason="consecutive_llm_errors:5")
    assert client.get("/api/ai-trader/status").json()["status"] == "error"
    r = client.post("/api/ai-trader/reset")
    assert r.status_code == 200
    assert client.get("/api/ai-trader/status").json()["status"] == "idle"


def test_live_arming_requires_confirm(monkeypatch, client):
    """Live mode + un-armed → start returns 409 with the required_confirm_text
    payload so the UI can show the exact phrase the operator must type."""
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: True)
    # Make sure no prior arming leaks across tests.
    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        row = load_or_create(s)
        row.armed_for_live_at = None
        s.commit()
    r = client.post("/api/ai-trader/start")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "live_arming_required"
    assert body["required_confirm_text"] == "I UNDERSTAND REAL MONEY"
    # Status must NOT have flipped to running while arming was refused.
    assert client.get("/api/ai-trader/status").json()["status"] != "running"


def test_live_arming_with_confirm_succeeds(monkeypatch, client):
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: True)
    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        row = load_or_create(s)
        row.armed_for_live_at = None
        s.commit()
    r = client.post(
        "/api/ai-trader/start",
        json={"confirm_text": "I UNDERSTAND REAL MONEY"},
    )
    assert r.status_code == 200
    st = client.get("/api/ai-trader/status").json()
    assert st["status"] == "running"
    assert st["armed_for_live_at"] is not None, (
        "armed_for_live_at must be persisted on first successful live arming"
    )


def test_live_arming_near_miss_rejected(monkeypatch, client):
    """Exact-match gate: a near miss (wrong case, extra whitespace, trailing
    punctuation) must be refused with 409 — not silently accepted."""
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: True)
    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        row = load_or_create(s)
        row.armed_for_live_at = None
        s.commit()
    for near_miss in (
        "i understand real money",        # wrong case
        "I UNDERSTAND REAL MONEY ",       # trailing whitespace
        "I UNDERSTAND REAL MONEY.",       # trailing punctuation
        " I UNDERSTAND REAL MONEY",       # leading whitespace
    ):
        r = client.post(
            "/api/ai-trader/start",
            json={"confirm_text": near_miss},
        )
        assert r.status_code == 409, (
            f"near-miss {near_miss!r} was accepted (got {r.status_code}); "
            "exact-match is required"
        )
        assert r.json()["error"] == "live_arming_required"
    # And after all the near-misses, armed_for_live_at must still be null.
    st = client.get("/api/ai-trader/status").json()
    assert st["armed_for_live_at"] is None


def test_first_live_arming_lowers_caps_to_conservative_tier(monkeypatch, client):
    """Per spec §11: first successful live arming downgrades the risk
    defaults to per-order 20 USDT, daily loss -10 USDT, daily max trades 10."""
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: True)
    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        row = load_or_create(s)
        row.armed_for_live_at = None
        # Pre-seed testnet-tier values so we can see them get lowered.
        row.max_order_quote_usdt = 50.0
        row.daily_loss_cap_usdt = -30.0
        row.daily_max_trades = 20
        s.commit()
    r = client.post(
        "/api/ai-trader/start",
        json={"confirm_text": "I UNDERSTAND REAL MONEY"},
    )
    assert r.status_code == 200
    st = client.get("/api/ai-trader/status").json()
    assert st["max_order_quote_usdt"] == 20.0
    assert st["daily_loss_cap_usdt"] == -10.0
    assert st["daily_max_trades"] == 10


def test_settings_put_updates_caps(client, _testnet_mode):
    r = client.put(
        "/api/ai-trader/settings",
        json={"max_order_quote_usdt": 25.0,
              "max_position_per_symbol_usdt": 250.0,
              "daily_loss_cap_usdt": -5.0,
              "daily_max_trades": 8,
              "symbols": ["BTCUSDT", "ETHUSDT"],
              "poll_interval_sec": 30},
    )
    assert r.status_code == 200
    st = client.get("/api/ai-trader/status").json()
    assert st["max_order_quote_usdt"] == 25.0
    assert st["max_position_per_symbol_usdt"] == 250.0
    assert st["daily_loss_cap_usdt"] == -5.0
    assert st["daily_max_trades"] == 8
    assert st["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert st["poll_interval_sec"] == 30


def test_settings_put_rejects_invalid_caps(client, _testnet_mode):
    """PUT /settings must refuse values that would defeat the guards.
    Each rule fires independently and returns 422."""
    # Per-order cap must be positive (otherwise the guard that uses it as
    # an upper bound becomes useless).
    r = client.put(
        "/api/ai-trader/settings",
        json={"max_order_quote_usdt": 0},
    )
    assert r.status_code == 422
    r = client.put(
        "/api/ai-trader/settings",
        json={"max_order_quote_usdt": -1},
    )
    assert r.status_code == 422
    # Per-symbol position cap must be positive for the same reason.
    r = client.put(
        "/api/ai-trader/settings",
        json={"max_position_per_symbol_usdt": 0},
    )
    assert r.status_code == 422
    # Daily loss cap is a negative number; a positive value inverts the guard
    # (pnl_today > positive cap would trip on a winning day, or never trip
    # on a losing day).
    r = client.put(
        "/api/ai-trader/settings",
        json={"daily_loss_cap_usdt": 5.0},
    )
    assert r.status_code == 422
    # Trade count must be >= 1.
    r = client.put(
        "/api/ai-trader/settings",
        json={"daily_max_trades": 0},
    )
    assert r.status_code == 422
    r = client.put(
        "/api/ai-trader/settings",
        json={"daily_max_trades": -3},
    )
    assert r.status_code == 422
    # And no row was mutated by the rejected requests.
    st = client.get("/api/ai-trader/status").json()
    assert st["max_order_quote_usdt"] > 0
    assert st["max_position_per_symbol_usdt"] > 0
    assert st["daily_loss_cap_usdt"] < 0
    assert st["daily_max_trades"] >= 1


def test_emergency_stop_blocks_subsequent_tick(client, monkeypatch):
    """After emergency-stop, status == "stopped" and tick() must not call
    the LLM and must not place an order. Use a double that fails loudly if
    invoked."""
    import asyncio
    from app.models.ai_decision import AIDecision

    # The full suite runs many tests that leave AIDecision rows behind.
    # Snapshot the count first and assert against the DELTA, not the
    # absolute count — otherwise state from prior tests would mask a
    # genuine regression where tick() writes rows after emergency-stop.
    with SessionLocal() as s:
        baseline = s.query(AIDecision).count()

    class BoomLLM:
        def __init__(self):
            self.calls = 0
        async def chat(self, *a, **k):
            self.calls += 1
            raise AssertionError("tick must not call LLM after emergency-stop")

    class BoomBroker:
        def __init__(self):
            self.place_calls = 0
        def get_klines(self, *a, **k):
            return [[0, "60000", "60100", "59900", "60050", "10"]] * 5
        def get_account_info(self):
            return {"balances": []}
        def get_open_orders(self, *a, **k):
            return []
        def place_order(self, *a, **k):
            self.place_calls += 1
            raise AssertionError("tick must not place an order after emergency-stop")

    llm = BoomLLM()
    broker = BoomBroker()
    monkeypatch.setattr(_svc.trader, "llm", llm)
    monkeypatch.setattr(_svc.trader, "broker", broker)
    # Confirm wiring took.
    assert _svc.trader.llm is llm
    assert _svc.trader.broker is broker

    # Start (testnet), then emergency-stop.
    monkeypatch.setattr(_svc, "_is_live_mode", lambda: False)
    assert client.post("/api/ai-trader/start").status_code == 200
    assert client.post("/api/ai-trader/emergency-stop").status_code == 200
    assert client.get("/api/ai-trader/status").json()["status"] == "stopped"

    # Now drive a tick. Because status != "running", tick() must return
    # BEFORE the LLM or broker is touched. Both doubles would raise if hit.
    asyncio.run(_svc.trader.tick())
    assert llm.calls == 0
    assert broker.place_calls == 0
    # No NEW decision rows either.
    with SessionLocal() as s:
        after = s.query(AIDecision).count()
    assert after == baseline, (
        f"tick after emergency-stop wrote {after - baseline} decision rows"
    )