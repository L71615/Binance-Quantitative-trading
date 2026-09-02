import json
from datetime import datetime, UTC

import pytest

from app.db import Base, SessionLocal, engine
from app.models.grid import Grid, GridStatus
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
        from app.models.order import Order
        s.query(Order).delete()
        from app.models.ai_settings import AISettings, load_or_create
        row = load_or_create(s)
        row.status = "idle"
        row.status_reason = None
        row.last_tick_at = None
        # Reset the LLM-error streak counter too — earlier tests in this
        # module (e.g. test_five_consecutive_llm_errors_trip_to_error) leave
        # the singleton at status=error with the counter pinned at 5, so a
        # test that wants to observe a fresh streak must zero it explicitly.
        row.consecutive_llm_errors = 0
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
    def __init__(self, *, symbol_info: dict | None = None):
        super().__init__()
        self.placed = []
        # Optional exchangeInfo stub for the precision-gate tests. When
        # `None` the broker reports "no precision info" and the service
        # passes values through unchanged — which is the right behaviour
        # for the pre-fix tests that don't care about rounding.
        self._symbol_info = symbol_info

    def place_order(self, symbol, side, type_, quantity, price=None, **kw):
        self.placed.append(
            {"symbol": symbol, "side": side, "type_": type_, "quantity": quantity,
             "price": price}
        )
        return {"orderId": 999, "status": "FILLED", "executedQty": str(quantity),
                "price": str(price)}

    def get_symbol_info(self, symbol):
        if self._symbol_info is None:
            return {}
        return self._symbol_info


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


@pytest.mark.asyncio
async def test_five_consecutive_parse_failures_trip_to_error(_fresh_state):
    """Final fix wave — Fix 2: 5 consecutive parse failures trip to status=error.

    Spec §5 ("解析失败或 HTTP 异常") lumps parse failures into the same
    tripwire bucket as HTTP exceptions: the LLM is unreachable in both
    senses. Before this fix the parse-failed branch passed `llm_error=False`
    so only HTTP exceptions counted; a perpetually misbehaving model that
    always returned un-parseable JSON would never trip. Asserting this
    pins the design decision and prevents a future regression that quietly
    reverts `llm_error=True` in this branch.
    """
    from app.services.ai_trader.service import AITraderService

    # LLM that returns syntactically-broken payloads — the upstream is up,
    # but every response is un-parseable.
    class GarbageLLM:
        async def chat(self, *a, **k):
            return "not json at all"

    s = AITraderService(llm=GarbageLLM(), broker=FakeBroker())
    s._set_status("running")
    for _ in range(5):
        await s.tick()
    st = s.status()
    assert st["status"] == "error", (
        f"parse failures must count toward the tripwire; got status={st['status']!r}"
    )
    assert "consecutive_llm_errors" in (st["status_reason"] or "")
    # Audit invariant: every tick that actually ran (status==running at tick
    # entry) wrote one no_trade row with error="parse_failed". Once the
    # tripwire flips status to error, tick() short-circuits without writing
    # — so we expect exactly as many rows as the streak that produced the
    # trip, which is at least 5 (the test loop), and they all carry the
    # parse_failed cause so the operator sees why each one was rejected.
    with SessionLocal() as db:
        rows = db.query(AIDecision).order_by(AIDecision.id).all()
    assert len(rows) >= 5
    assert all(r.outcome == "no_trade" for r in rows)
    assert all((r.error or "") == "parse_failed" for r in rows)


# -- Final fix wave — Fix 3: round qty/price to exchange precision -------


def _btcusdt_precision(*, step: float, tick: float, min_notional: float) -> dict:
    """Build the minimal Binance exchangeInfo fragment that
    `AITraderService._apply_exchange_precision` consumes. Shape mirrors
    `BinanceClient.get_symbol_info` (the response of /api/v3/exchangeInfo).
    """
    return {
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": step},
            {"filterType": "PRICE_FILTER", "tickSize": tick},
            {"filterType": "MIN_NOTIONAL", "minNotional": min_notional},
        ],
    }


@pytest.mark.asyncio
async def test_tick_rounds_qty_and_price_to_exchange_precision(_fresh_state):
    """LLM emits a qty and a price that violate LOT_SIZE / PRICE_FILTER.
    The precision helper must round them BEFORE calling place_order so
    Binance never sees a value it will reject with -1013 / -1019. Catches
    a regression where _tick_symbol skipped the rounding path.
    """
    from app.services.ai_trader.service import AITraderService
    from app.models.ai_settings import load_or_create

    broker = OrderCapturingBroker(
        symbol_info=_btcusdt_precision(
            step=0.00001, tick=0.01, min_notional=10.0,
        )
    )
    llm = FakeLLM([json.dumps(
        # qty 0.0003333 isn't a multiple of 0.00001; price 60123.4567
        # isn't a multiple of 0.01; notional >> min_notional so the
        # MIN_NOTIONAL guard stays out of the way here.
        {"action": "buy", "symbol": "BTCUSDT",
         "qty": 0.0003333, "price": 60123.4567,
         "reason": "raw LLM output, unrounded"})])
    s = AITraderService(llm=llm, broker=broker)
    s._set_status("running")
    with SessionLocal() as db:
        row = load_or_create(db)
        row.max_order_quote_usdt = 1000.0
        db.commit()
    await s.tick()
    # The broker received the ROUNDED ones, not the raw LLM ones.
    assert len(broker.placed) == 1
    placed = broker.placed[0]
    assert placed["quantity"] == 0.00033  # floor(0.0003333 / 0.00001) * 0.00001
    assert placed["price"] == 60123.46   # round(60123.4567 / 0.01) * 0.01
    # And the audit row carries the rounded values too, so what the
    # operator sees in /decisions matches what Binance saw.
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "placed"
    parsed_back = json.loads(rows[0].parsed)
    assert parsed_back["qty"] == 0.00033
    assert parsed_back["price"] == 60123.46


@pytest.mark.asyncio
async def test_tick_rejects_below_min_notional_without_calling_place_order(
    _fresh_state,
):
    """When the rounded notional is below MIN_NOTIONAL, the tick must NOT
    call place_order. It must write a `rejected` audit row carrying
    `error="below_min_notional:<value>"` so the operator (and the LLM)
    see why the order was skipped. Catches a regression that either
    calls place_order with too-small values or fails to write the
    audit row.
    """
    from app.services.ai_trader.service import AITraderService
    from app.models.ai_settings import load_or_create

    broker = OrderCapturingBroker(
        symbol_info=_btcusdt_precision(
            step=0.00001, tick=0.01, min_notional=10.0,
        )
    )
    llm = FakeLLM([json.dumps(
        # notional = 0.001 * 5000 = 5 USDT, well under 10 USDT MIN_NOTIONAL
        {"action": "buy", "symbol": "BTCUSDT",
         "qty": 0.001, "price": 5000.0,
         "reason": "tiny order, will fail MIN_NOTIONAL"})])
    s = AITraderService(llm=llm, broker=broker)
    s._set_status("running")
    with SessionLocal() as db:
        row = load_or_create(db)
        row.max_order_quote_usdt = 1000.0
        db.commit()
    await s.tick()
    # Broker never saw this — precision gate rejected before place_order.
    assert broker.placed == [], (
        f"place_order was called despite sub-MIN_NOTIONAL notional: "
        f"{broker.placed!r}"
    )
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "rejected"
    assert (rows[0].error or "").startswith("below_min_notional:"), (
        f"audit row must carry below_min_notional:<value>; got {rows[0].error!r}"
    )


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


# -- Final fix wave — Fix 1: Guard 6 wired to the Order table --------------
#
# Before this fix `AITraderService.__init__` defaulted `grid_has_open_orders`
# to `lambda s: False`, so Guard 6 (`symbol_exclusive`) always passed and two
# systems could stack positions on the same symbol. These two tests pin the
# new default: the callback must return True when an open Order row exists
# for the requested symbol, False otherwise, and the result must not leak
# across symbols.


def _seed_open_order(symbol: str) -> None:
    """Insert one Grid + one Order(status=NEW) row for `symbol`.

    `Order.grid_id` is `NOT NULL` and FK-constrained, so a parent Grid is
    required. Both rows live just for the duration of the test; the
    `_fresh_state` fixture tears them down.
    """
    from app.models.order import Order
    with SessionLocal() as s:
        g = Grid(
            symbol=symbol, lower_price=1.0, upper_price=2.0, grid_count=3,
            grid_mode="arithmetic", total_quote_amount=10.0,
            status=GridStatus.RUNNING,
            created_at=datetime.now(UTC),
        )
        s.add(g)
        s.flush()
        s.add(Order(
            grid_id=g.id, binance_order_id=10_000 + abs(hash(symbol)) % 1_000_000,
            symbol=symbol, side="BUY", type="LIMIT", price=1.5, qty=0.001,
            filled_qty=0.0, status="NEW",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        ))
        s.commit()


def test_grid_has_open_orders_true_when_new_order_exists(_fresh_state):
    """Guard 6 callback must return True when an Order(status=NEW) row exists
    for the symbol. Regression-protects the wiring of the Order table.
    """
    from app.services.ai_trader.service import AITraderService
    _seed_open_order("BTCUSDT")
    s = AITraderService()
    assert s.grid_has_open_orders("BTCUSDT") is True


def test_grid_has_open_orders_false_when_no_orders_and_no_symbol_leak(
    _fresh_state,
):
    """Guard 6 callback must return False when no orders exist for the
    symbol, and True for one symbol must not leak to another.
    """
    from app.services.ai_trader.service import AITraderService
    # No orders at all → False.
    s = AITraderService()
    assert s.grid_has_open_orders("BTCUSDT") is False
    assert s.grid_has_open_orders("ETHUSDT") is False
    # Seed BTCUSDT only, then ask about ETHUSDT — must stay False.
    _seed_open_order("BTCUSDT")
    assert s.grid_has_open_orders("BTCUSDT") is True
    assert s.grid_has_open_orders("ETHUSDT") is False, (
        "Guard 6 callback must filter by symbol; the 'any open order means "
        "every symbol is blocked' bug would leak BTCUSDT's open order onto "
        "ETHUSDT and silently disable half the AI Trader's universe"
    )
