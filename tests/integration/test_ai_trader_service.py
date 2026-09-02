import json
from datetime import datetime, UTC

import pytest

from app.db import Base, SessionLocal, engine
from app.services.ai_trader.service import AITraderService


def setup_module(_):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_initial_status_is_idle():
    s = AITraderService()
    assert s.status()["status"] == "idle"


def test_pause_and_resume_round_trip(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: type("Cfg", (), {"binance_testnet": True})())
    s = AITraderService()
    # The actual method sync_run below
    s._set_status("running")
    s.pause()
    assert s.status()["status"] == "paused"
    s.resume()
    assert s.status()["status"] == "running"


def test_emergency_stop_from_running(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: type("Cfg", (), {"binance_testnet": True})())
    s = AITraderService()
    s._set_status("running")
    s.emergency_stop()
    assert s.status()["status"] == "stopped"


def test_reset_from_stopped_to_idle():
    s = AITraderService()
    s._set_status("stopped")
    s.reset()
    assert s.status()["status"] == "idle"


def test_tick_placeholder_updates_last_tick_at():
    import asyncio
    s = AITraderService()
    s._set_status("running")
    asyncio.run(s.tick())
    st = s.status()
    assert st["last_tick_at"] is not None


# -- Task 8: full tick loop (context -> prompt -> llm -> parser -> guards -> audit) -----

from app.models.ai_decision import AIDecision  # noqa: E402


@pytest.fixture
def _fresh_state():
    """Reset ai_decision rows + revert ai_settings to defaults (idle)."""
    with SessionLocal() as s:
        s.query(AIDecision).delete()
        from app.models.ai_settings import AISettings, load_or_create
        row = load_or_create(s)
        row.status = "idle"
        row.status_reason = None
        row.last_tick_at = None
        row.symbols = '["BTCUSDT"]'
        s.commit()
    yield


class FakeLLM:
    """Returns a queue of canned responses, then a default hold."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def chat(self, messages, **kw):
        self.calls += 1
        if not self._responses:
            return json.dumps({"action": "hold", "symbol": "BTCUSDT",
                               "qty": 0, "price": 0, "reason": "queue empty"})
        return self._responses.pop(0)


class FakeBroker:
    def get_klines(self, symbol, interval, limit):
        return [[0, "60000", "60100", "59900", "60050", "10"]] * 5

    def get_account_info(self):
        return {"balances": [{"asset": "BTC", "free": "0.005", "locked": "0.001"}]}

    def get_open_orders(self, symbol=None):
        return []


@pytest.mark.asyncio
async def test_tick_skip_when_not_running(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(llm=FakeLLM([]), broker=FakeBroker())
    await s.tick()  # status is idle
    with SessionLocal() as db:
        n = db.query(AIDecision).count()
    assert n == 0


@pytest.mark.asyncio
async def test_tick_writes_decision_row_on_hold(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(
        llm=FakeLLM([json.dumps(
            {"action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0,
             "reason": "no setup right now"})]),
        broker=FakeBroker(),
    )
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].action == "hold"
    assert rows[0].outcome == "no_trade"


@pytest.mark.asyncio
async def test_tick_records_parse_failure_on_malformed_json(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(
        llm=FakeLLM(["not json at all"]),
        broker=FakeBroker(),
    )
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "no_trade"
    assert "parse_failed" in (rows[0].error or "")


@pytest.mark.asyncio
async def test_tick_marks_error_on_llm_exception(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS

    class BoomLLM:
        async def chat(self, *a, **k):
            raise RuntimeError("upstream down")

    s = _ATS(llm=BoomLLM(), broker=FakeBroker())
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "error"
    assert "upstream down" in (rows[0].error or "")


class OrderCapturingBroker(FakeBroker):
    def __init__(self):
        super().__init__()
        self.placed = []

    def place_order(self, symbol, side, type_, quantity, price=None, **kw):
        self.placed.append(
            {"symbol": symbol, "side": side, "type_": type_, "quantity": quantity,
             "price": price}
        )
        return {"orderId": 999, "status": "FILLED", "executedQty": str(quantity),
                "price": str(price)}


@pytest.mark.asyncio
async def test_tick_places_buy_order_when_guards_pass(_fresh_state):
    from app.services.ai_trader.service import AITraderService
    broker = OrderCapturingBroker()
    llm = FakeLLM([json.dumps(
        {"action": "buy", "symbol": "BTCUSDT", "qty": 0.001, "price": 30000,
         "reason": "small test buy under per-order cap"})])
    s = AITraderService(llm=llm, broker=broker)
    s._set_status("running")
    # Set per-order cap high enough that 30 USDT passes
    with SessionLocal() as db:
        from app.models.ai_settings import load_or_create
        row = load_or_create(db)
        row.max_order_quote_usdt = 100.0
        db.commit()
    await s.tick()
    assert len(broker.placed) == 1
    placed = broker.placed[0]
    assert placed["symbol"] == "BTCUSDT"
    assert placed["side"] == "buy"
    assert placed["quantity"] == 0.001
    assert placed["price"] == 30000
    # Decision row outcome=placed
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert rows[0].outcome == "placed"
    assert rows[0].order_id == "999"


# -- Task 10: tripwires (daily_loss / daily_trades / 5x LLM errors) -------------------


@pytest.mark.asyncio
async def test_daily_loss_cap_trips_to_paused(_fresh_state):
    """When a tick's pnl_today < daily_loss_cap_usdt, the daily_loss_cap guard
    fires, the tripwire sets status=paused with reason 'daily_loss_cap_hit'."""
    from app.services.ai_trader.service import AITraderService
    from app.models.ai_settings import load_or_create

    broker = OrderCapturingBroker()
    llm = FakeLLM([
        json.dumps({"action": "buy", "symbol": "BTCUSDT", "qty": 0.001,
                    "price": 30000, "reason": "small accumulating buy"}),
    ])
    s = AITraderService(llm=llm, broker=broker)
    s._set_status("running")
    # Construct state where the daily_loss guard genuinely fires:
    # pre-seed today's pnl so it is well below the cap, and disable the
    # per-order cap so the LLM buy actually reaches the daily_loss guard.
    with SessionLocal() as db:
        row = load_or_create(db)
        row.max_order_quote_usdt = 1000.0
        row.daily_loss_cap_usdt = -0.01
        # placed-sell with negative price → revenue = (-1.0)(1.0) = -1.0,
        # so today's pnl = -1.0, which is < -0.01 → guard fires.
        db.add(AIDecision(
            ts=datetime.now(UTC), symbol="BTCUSDT",
            market_snapshot="{}", prompt="seed", raw_response="seed",
            parsed=None, action="sell", guard_results="[]",
            outcome="placed", filled_qty=1.0, filled_price=-1.0,
        ))
        db.commit()
    await s.tick()
    st = s.status()
    assert st["status"] == "paused", (
        f"expected paused after daily-loss tripwire; got {st!r}"
    )
    assert (st["status_reason"] or "") == "daily_loss_cap_hit"


@pytest.mark.asyncio
async def test_daily_trades_cap_trips_to_paused(_fresh_state):
    """When trades_today >= daily_max_trades, the daily_trades_cap guard
    fires and the tripwire sets status=paused with 'daily_trades_cap_hit'."""
    from app.services.ai_trader.service import AITraderService
    from app.models.ai_settings import load_or_create

    broker = OrderCapturingBroker()
    llm = FakeLLM([
        json.dumps({"action": "hold", "symbol": "BTCUSDT", "qty": 0,
                    "price": 0, "reason": "hold but guard will still fire"}),
    ])
    s = AITraderService(llm=llm, broker=broker)
    s._set_status("running")
    with SessionLocal() as db:
        row = load_or_create(db)
        row.daily_max_trades = 3
        # Loss cap far below any realistic loss so daily_loss_cap guard
        # does not fire before daily_trades_cap (short-circuits).
        row.daily_loss_cap_usdt = -1_000_000.0
        # Pre-seed 3 placed rows today so trades_today (3) >= daily_max_trades (3).
        # filled_price=0 keeps today's pnl at 0, so daily_loss guard stays green.
        for _ in range(3):
            db.add(AIDecision(
                ts=datetime.now(UTC), symbol="BTCUSDT",
                market_snapshot="{}", prompt="seed", raw_response="seed",
                parsed=None, action="buy", guard_results="[]",
                outcome="placed",
                filled_qty=0.0, filled_price=0.0,
            ))
        db.commit()
    await s.tick()
    st = s.status()
    assert st["status"] == "paused", (
        f"expected paused after daily-trades tripwire; got {st!r}"
    )
    assert (st["status_reason"] or "") == "daily_trades_cap_hit"


@pytest.mark.asyncio
async def test_five_consecutive_llm_errors_trip_to_error(_fresh_state):
    """5 consecutive LLM exceptions trip the service to status=error."""
    from app.services.ai_trader.service import AITraderService

    class AlwaysBoom:
        async def chat(self, *a, **k):
            raise RuntimeError("upstream down")

    s = AITraderService(llm=AlwaysBoom(), broker=FakeBroker())
    s._set_status("running")
    for _ in range(5):
        await s.tick()
    st = s.status()
    assert st["status"] == "error"
    assert "consecutive_llm_errors" in (st["status_reason"] or "")


# -- Task 11 fix pass 2: wiring setters preserve flag invariant ---------


def test_wiring_setters_keep_flags_consistent():
    """set_broker / set_llm must atomically maintain the wiring_ok flag
    invariant:
        wiring_ok == broker_wired and llm_wired
    so a future code path (Task 12 control endpoints, PUT /settings, ...)
    can rewire the singleton without leaving /status under- or over-reporting.
    """
    from app.services.ai_trader.service import AITraderService

    # Start cold: no broker, no LLM.
    s = AITraderService()
    assert s.wiring_ok is False
    assert s.status()["wiring_ok"] is False
    assert s.status()["broker_wired"] is False
    assert s.status()["llm_wired"] is False

    # Wire only the broker — still not fully wired (no LLM).
    s.set_broker(FakeBroker())
    st = s.status()
    assert st["broker_wired"] is True
    assert st["llm_wired"] is False
    assert st["wiring_ok"] is False, (
        "wiring_ok must stay False until both broker and llm are present"
    )

    # Now wire the LLM — fully wired.
    s.set_llm(FakeLLM([]))
    st = s.status()
    assert st["broker_wired"] is True
    assert st["llm_wired"] is True
    assert st["wiring_ok"] is True

    # Unwire the broker — back to not-fully-wired. wiring_ok flips False.
    s.set_broker(None)
    st = s.status()
    assert st["broker_wired"] is False
    assert st["llm_wired"] is True
    assert st["wiring_ok"] is False, (
        "wiring_ok must flip False the moment one side is unwired"
    )

    # Re-wire broker — fully wired again. Flags must remain consistent.
    s.set_broker(FakeBroker())
    st = s.status()
    assert st["broker_wired"] is True
    assert st["llm_wired"] is True
    assert st["wiring_ok"] is True

# -- Task 11 fix pass 3: wiring_ok is derived, not stored -----------------


def test_wiring_ok_is_derived_identically_via_constructor_and_setters():
    """`wiring_ok` must depend ONLY on the client state — never on HOW that
    state arrived.

    Regression guard for the fix-pass-3 defect: `__init__` used to compute
    `wiring_ok = broker is not None` (ignoring llm) while the setters
    computed `broker is not None and llm is not None`. Identical client
    state therefore reported a different wiring_ok depending on whether it
    came from the constructor or a setter. Assert every one of the four
    client combinations agrees across both construction paths.
    """
    from app.services.ai_trader.service import AITraderService

    for want_broker in (False, True):
        for want_llm in (False, True):
            broker = FakeBroker() if want_broker else None
            llm = FakeLLM([]) if want_llm else None
            expected = want_broker and want_llm

            # Path A: via the constructor.
            a = AITraderService(broker=broker, llm=llm)
            # Path B: cold, then via the setters.
            b = AITraderService()
            b.set_broker(broker)
            b.set_llm(llm)

            assert a.wiring_ok is expected, (
                f"constructor(broker={want_broker}, llm={want_llm}) gave "
                f"wiring_ok={a.wiring_ok}, expected {expected}"
            )
            assert b.wiring_ok is expected, (
                f"setters(broker={want_broker}, llm={want_llm}) gave "
                f"wiring_ok={b.wiring_ok}, expected {expected}"
            )
            assert a.wiring_ok == b.wiring_ok, (
                "wiring_ok differs between constructor and setter paths for "
                f"identical client state (broker={want_broker}, llm={want_llm})"
            )
            # /status must agree with the attribute, and the three flags
            # must be mutually consistent.
            for svc in (a, b):
                st = svc.status()
                assert st["broker_wired"] is want_broker
                assert st["llm_wired"] is want_llm
                assert st["wiring_ok"] is expected
                assert st["wiring_ok"] == (
                    st["broker_wired"] and st["llm_wired"]
                )


def test_wiring_ok_cannot_be_forced_out_of_sync():
    """`wiring_ok` is a read-only derived property: no code path (including
    a future Task 12 control endpoint or main.py's exception handler) can
    pin it to a value that contradicts the clients."""
    from app.services.ai_trader.service import AITraderService

    s = AITraderService(broker=FakeBroker(), llm=FakeLLM([]))
    assert s.wiring_ok is True
    # Attempting to force the flag must fail loudly rather than create drift.
    with pytest.raises(AttributeError):
        s.wiring_ok = False
    assert s.wiring_ok is True, "wiring_ok was mutated despite the raise"
    # The honest way to express "not wired" is to clear the clients.
    s.set_broker(None)
    s.set_llm(None)
    st = s.status()
    assert st["wiring_ok"] is False
    assert st["broker_wired"] is False
    assert st["llm_wired"] is False
