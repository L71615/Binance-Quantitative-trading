import asyncio
from datetime import datetime, UTC

import pytest

from app.db import Base, SessionLocal, engine
from app.models.grid import Grid, GridStatus


def setup_module(_):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _clean_db_between_tests():
    """Truncate the Order table between tests so prior runs' rows don't
    cause UNIQUE-constraint conflicts against the placeholder ids minted
    by the next test."""
    from app.models.order import Order
    with SessionLocal() as s:
        s.query(Order).delete()
        s.commit()
    yield
    with SessionLocal() as s:
        s.query(Order).delete()
        s.commit()


@pytest.mark.asyncio
async def test_grid_lifecycle_runs_strategy_and_broadcasts_status():
    from app.engine.lifecycle import Lifecycle

    lc = Lifecycle()
    await lc.start()
    events = []
    lc.on_event(lambda e: events.append(e))
    await lc.start_grid(grid_id=42, symbol="BTCUSDT", lower=1.0, upper=2.0,
                        count=3, mode="arithmetic", total_quote_amount=10.0)
    await asyncio.sleep(0.1)
    await lc.stop_grid(grid_id=42)
    await lc.stop()
    types = [e["type"] for e in events]
    assert "grid_running" in types
    assert "grid_stopped" in types


# -- Final fix wave: Grid order persistence ---------------------------------
#
# These tests pin the contract that `Lifecycle.start_grid` writes a row to
# the `Order` table for every order it places, so Guard 6
# (`symbol_exclusive`) in the AI Trader can actually SEE live grid activity.
#
# Pre-fix: the in-memory `place_order` closure fires an event and returns
# `{"orderId": 0}` — no DB write. Guard 6 in production would silently
# miss every grid order. The first test below is the regression guard.


class _RecordingBroker:
    """Captures place_order calls and returns a plausible exchange reply.

    Replaces `Lifecycle._place_order_via_broker` via monkeypatch; the
    lifecycle still owns the row-write side and observes the result here.

    Mints a unique `orderId` per call so the lifecycle's post-call
    UPDATE doesn't trip the binance_order_id UNIQUE constraint. Real
    Binance obviously does this naturally; the fake has to simulate it.
    """

    def __init__(self):
        self.calls = []
        self._next_id = 5000

    def __call__(self, *, symbol, side, type_, quantity, price):
        self.calls.append(
            {"symbol": symbol, "side": side, "type_": type_,
             "quantity": quantity, "price": price}
        )
        oid = self._next_id
        self._next_id += 1
        # Mimic Binance's response shape: orderId, status, executedQty, price.
        return {
            "orderId": oid,
            "status": "NEW",
            "executedQty": "0",
            "price": str(price),
        }


def _seed_grid(symbol: str = "BTCUSDT") -> int:
    """Insert a Grid row so the FK constraint on Order.grid_id is satisfied."""
    with SessionLocal() as s:
        g = Grid(
            symbol=symbol, lower_price=1.0, upper_price=2.0, grid_count=3,
            grid_mode="arithmetic", total_quote_amount=10.0,
            status=GridStatus.RUNNING,
            created_at=datetime.now(UTC),
        )
        s.add(g)
        s.commit()
        return g.id


@pytest.mark.asyncio
async def test_start_grid_persists_order_rows_to_order_table(monkeypatch):
    """RED: Lifecycle.start_grid must write an Order row per place_order call.

    Guards 6 (`symbol_exclusive`) reads the Order table to detect live grid
    exposure. Without this write, Guard 6 sees no grid orders and lets the
    AI Trader stack positions on the same symbol. Catches any future
    regression that bypasses the DB write.
    """
    from app.engine.lifecycle import Lifecycle

    grid_id = _seed_grid("BTCUSDT")
    broker = _RecordingBroker()

    # Monkeypatch the broker-call helper the lifecycle uses. Pre-fix this
    # attribute does not exist, so the lifecycle's in-memory callback fires
    # an event and never persists — the test then asserts an Order row
    # exists, which fails.
    monkeypatch.setattr(
        "app.engine.lifecycle._place_order_via_broker", broker,
        raising=False,
    )

    lc = Lifecycle()
    await lc.start()
    try:
        await lc.start_grid(
            grid_id=grid_id, symbol="BTCUSDT", lower=1.0, upper=2.0,
            count=4, mode="arithmetic", total_quote_amount=10.0,
        )
        # Let any async tasks settle.
        await asyncio.sleep(0.05)
    finally:
        await lc.stop_grid(grid_id=grid_id)
        await lc.stop()

    # Broker was actually called by the strategy.
    assert len(broker.calls) >= 1, (
        f"lifecycle did not route place_order to the broker: {broker.calls!r}"
    )
    # AND the Order table has at least one row matching the grid's symbol.
    from app.models.order import Order
    with SessionLocal() as s:
        rows = (
            s.query(Order)
            .filter(Order.grid_id == grid_id, Order.symbol == "BTCUSDT")
            .all()
        )
    assert len(rows) >= 1, (
        "Lifecycle.start_grid placed orders but did NOT persist any Order "
        "rows — Guard 6 cannot see live grid activity. Pre-fix regression."
    )
    # And the row's status reflects the exchange reply ("NEW" by default).
    assert rows[0].status == "NEW", (
        f"persisted Order row must carry status='NEW' from the exchange "
        f"reply; got {rows[0].status!r}"
    )


@pytest.mark.asyncio
async def test_start_grid_persists_status_from_exchange_response(monkeypatch):
    """GREEN companion: the persisted row's status mirrors the exchange's
    reply, not a hardcoded string. A filled-reply produces status='FILLED'.
    """
    from app.engine.lifecycle import Lifecycle

    grid_id = _seed_grid("BTCUSDT")

    class FilledBroker:
        def __init__(self):
            self._next_id = 7000

        def __call__(self, *, symbol, side, type_, quantity, price):
            oid = self._next_id
            self._next_id += 1
            return {
                "orderId": oid,
                "status": "FILLED",
                "executedQty": str(quantity),
                "price": str(price),
            }

    monkeypatch.setattr(
        "app.engine.lifecycle._place_order_via_broker", FilledBroker(),
        raising=False,
    )

    lc = Lifecycle()
    await lc.start()
    try:
        await lc.start_grid(
            grid_id=grid_id, symbol="BTCUSDT", lower=1.0, upper=2.0,
            count=4, mode="arithmetic", total_quote_amount=10.0,
        )
        await asyncio.sleep(0.05)
    finally:
        await lc.stop_grid(grid_id=grid_id)
        await lc.stop()

    from app.models.order import Order
    with SessionLocal() as s:
        rows = (
            s.query(Order)
            .filter(Order.grid_id == grid_id)
            .all()
        )
    assert len(rows) >= 1
    statuses = {r.status for r in rows}
    assert "FILLED" in statuses, (
        f"persisted Order rows must reflect exchange reply 'FILLED'; "
        f"got statuses={statuses!r}"
    )


# -- Cross-feature: AI Trader Guard 6 sees a real grid row -------------------
#
# These two tests pin the cross-feature wiring: seed an Order(status=NEW)
# row directly (the path the GridTrader would populate post-fix) and
# assert that AITraderService.grid_has_open_orders returns the right
# thing. Together they prove Guard 6 is wired and that the status filter
# actually filters (not a vacuous constant).


def _seed_open_order(symbol: str, *, status: str = "NEW") -> None:
    """Insert a Grid + one Order row with the given status.

    Same shape as the AI Trader test fixture `_seed_open_order` but kept
    local here so the lifecycle tests don't depend on the AI Trader test
    module's import order.
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
            grid_id=g.id,
            binance_order_id=10_000 + abs(hash(symbol + status)) % 1_000_000,
            symbol=symbol, side="BUY", type="LIMIT", price=1.5, qty=0.001,
            filled_qty=0.0, status=status,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        ))
        s.commit()


@pytest.fixture
def _fresh_state():
    """Reset the Order table between tests so seeded rows don't leak."""
    from app.models.order import Order
    with SessionLocal() as s:
        s.query(Order).delete()
        s.commit()
    yield


def test_guard_6_returns_true_when_grid_persisted_a_new_order(_fresh_state):
    """Cross-feature: a real grid-style Order(status=NEW) row, seeded the
    way the (post-fix) GridTrader would produce it, is detected by the
    AI Trader's Guard 6 callback. Confirms Guard 6's wiring is intact
    AND that the grid side now supplies the rows it expects.
    """
    from app.services.ai_trader.service import AITraderService
    _seed_open_order("BTCUSDT", status="NEW")
    s = AITraderService()
    assert s.grid_has_open_orders("BTCUSDT") is True


def test_guard_6_status_filter_is_not_a_vacuous_constant(_fresh_state):
    """Status transitions: a filled grid order is NOT an open order.
    Mutating the seeded row's status from NEW → FILLED must flip the
    Guard 6 callback to False — proving the status filter actually
    filters, and ruling out a future regression that broadens the
    filter (e.g. dropping the status predicate) or hardcodes True.
    """
    from app.models.order import Order
    from app.services.ai_trader.service import AITraderService
    _seed_open_order("BTCUSDT", status="NEW")

    s = AITraderService()
    # NEW → open: True.
    assert s.grid_has_open_orders("BTCUSDT") is True

    # Mutate to FILLED → open: False.
    with SessionLocal() as db:
        row = db.query(Order).filter(Order.symbol == "BTCUSDT").first()
        row.status = "FILLED"
        db.commit()

    assert s.grid_has_open_orders("BTCUSDT") is False, (
        "Guard 6 status filter must reject status='FILLED'; if this is "
        "False, the filter is not actually filtering."
    )