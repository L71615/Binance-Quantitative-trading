"""P0-1 (CEO plan OV-C): paper-trading P&L must not bleed into live counters.

Pre-fix: AIDecision had no is_paper column and _compute_today_counters
queried every placed row. A morning of bad paper fills silently tripped
the live daily_loss_cap and halted live trading.

These tests pin the post-fix contract:
  1. AIDecision defaults is_paper=False (live).
  2. _compute_today_counters filters by service.is_paper.
  3. paper placed rows do NOT move live pnl_today or trades_today.
  4. Migration is idempotent — re-running on an already-migrated DB is a
     no-op and the existing rows survive untouched.
"""
import json
from datetime import datetime, UTC

import pytest

from app.db import Base, SessionLocal, engine
from app.migrations import run_all_migrations
from app.models.ai_decision import AIDecision
from app.services.ai_trader.service import AITraderService


@pytest.fixture(autouse=True)
def _clean_db():
    """Each test gets a fresh DB so row-count assertions stay deterministic."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)
    yield
    Base.metadata.drop_all(engine)


def test_ai_decision_defaults_is_paper_false():
    with SessionLocal() as s:
        s.add(AIDecision(
            symbol="BTCUSDT",
            market_snapshot="{}",
            prompt="p",
            raw_response="r",
            action="hold",
            guard_results="[]",
            outcome="no_trade",
        ))
        s.commit()
        row = s.query(AIDecision).one()
        assert row.is_paper is False, (
            "Default must be live (False). Existing live rows post-migration "
            "should all read False so counters behave unchanged."
        )


def test_compute_today_counters_separates_paper_from_live():
    """The headline regression test: paper P&L must not move live counters."""
    now = datetime.now(UTC)

    # 1 placed paper sell @ 100, qty 1 → paper revenue +$100
    # 1 placed live buy  @ 100, qty 1 → live cost     -$100
    # Without is_paper filter: pnl_today = 100 - 100 = 0 (cancels)
    # With    is_paper filter: live pnl_today = -100 (cost only),
    #                         paper pnl_today = +100
    paper_row = AIDecision(
        symbol="BTCUSDT",
        market_snapshot="{}",
        prompt="p",
        raw_response="r",
        parsed=json.dumps({"action": "sell", "qty": 1, "price": 100}),
        action="sell",
        guard_results="[]",
        outcome="placed",
        filled_qty=1.0,
        filled_price=100.0,
        is_paper=True,
        ts=now,
    )
    live_row = AIDecision(
        symbol="BTCUSDT",
        market_snapshot="{}",
        prompt="p",
        raw_response="r",
        parsed=json.dumps({"action": "buy", "qty": 1, "price": 100}),
        action="buy",
        guard_results="[]",
        outcome="placed",
        filled_qty=1.0,
        filled_price=100.0,
        is_paper=False,
        ts=now,
    )
    with SessionLocal() as s:
        s.add_all([paper_row, live_row])
        s.commit()

    live_svc = AITraderService(is_paper=False)
    pnl, trades = live_svc._compute_today_counters()
    assert trades == 1, f"live should see only its own 1 trade, got {trades}"
    assert pnl == pytest.approx(-100.0), (
        f"live pnl_today should be -100 (only the buy cost). Got {pnl}. "
        "If pnl ≈ 0 the paper row leaked into live counters — OV-C regressed."
    )

    paper_svc = AITraderService(is_paper=True)
    pnl, trades = paper_svc._compute_today_counters()
    assert trades == 1, f"paper should see only its own 1 trade, got {trades}"
    assert pnl == pytest.approx(100.0), (
        f"paper pnl_today should be +100 (only the sell revenue). Got {pnl}."
    )


def test_write_decision_stamps_is_paper_from_service():
    """_write_decision must derive is_paper from self.is_paper, not require
    callers to pass it (else a paper-mode bug regresses silently)."""
    paper_svc = AITraderService(is_paper=True)
    paper_svc._write_decision(
        symbol="BTCUSDT",
        market_snapshot="{}",
        prompt="p",
        raw_response="r",
        action="hold",
        guard_results="[]",
        outcome="no_trade",
    )
    with SessionLocal() as s:
        # Just-added row: filter by symbol so we only see what this test wrote.
        paper_rows = (
            s.query(AIDecision).filter(AIDecision.symbol == "BTCUSDT").all()
        )
        assert len(paper_rows) == 1
        assert paper_rows[0].is_paper is True

    live_svc = AITraderService(is_paper=False)
    live_svc._write_decision(
        symbol="ETHUSDT",  # different symbol so the assertion stays unambiguous
        market_snapshot="{}",
        prompt="p",
        raw_response="r",
        action="hold",
        guard_results="[]",
        outcome="no_trade",
    )
    with SessionLocal() as s:
        eth_row = s.query(AIDecision).filter(AIDecision.symbol == "ETHUSDT").one()
        assert eth_row.is_paper is False


def test_migration_is_idempotent():
    """Re-running run_all_migrations on a migrated DB must not raise and must
    not corrupt existing data. The PRAGMA check should skip the ALTER."""
    with SessionLocal() as s:
        s.add(AIDecision(
            symbol="BTCUSDT",
            market_snapshot="{}",
            prompt="p",
            raw_response="r",
            action="hold",
            guard_results="[]",
            outcome="no_trade",
        ))
        s.commit()
        before = s.query(AIDecision).count()

    # Re-run migration — this is the contract under test.
    run_all_migrations(engine)

    with SessionLocal() as s:
        after = s.query(AIDecision).count()
        assert after == before, "migration must not delete rows"
        for row in s.query(AIDecision).all():
            assert isinstance(row.is_paper, bool)

