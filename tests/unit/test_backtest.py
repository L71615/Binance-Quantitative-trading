"""P0-5 (CEO plan OV-B): backtest pipeline pins the proof-of-strategy
contract.

End-to-end flow:
  1. ReplayLLM returns stored raw_response strings in chronological order.
  2. HistoricalBroker satisfies the Broker interface against frozen K-lines
     and a virtual ledger.
  3. metrics.summarise computes Sharpe / DD / win rate from fills.
  4. report.render_report turns the summary into a static HTML file.
  5. run_backtest orchestrates everything and writes the HTML to disk.

Tests pin each piece independently so a regression in one (e.g.
Sharpe flipping sign) fails at the right place.
"""
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

import pytest

from app.backtest.metrics import (
    equity_curve,
    max_drawdown,
    sharpe_ratio,
    summarise,
    win_rate,
)
from app.backtest.report import render_report
from app.backtest.runner import run_backtest
from app.broker.historical import HistoricalBroker
from app.db import Base, SessionLocal, engine
from app.migrations import run_all_migrations
from app.services.ai_trader.replay_llm import ReplayLLM
from app.services.llm import LLMError


# ----- ReplayLLM --------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_returns_stored_responses_in_order():
    rows = [_row("a"), _row("b"), _row("c")]
    rl = ReplayLLM(rows)
    assert await rl.chat([]) == "a"
    assert await rl.chat([]) == "b"
    assert await rl.chat([]) == "c"


@pytest.mark.asyncio
async def test_replay_exhausts_with_clear_error():
    rl = ReplayLLM([_row("only")])
    assert await rl.chat([]) == "only"
    with pytest.raises(LLMError) as exc_info:
        await rl.chat([])
    assert "replay_exhausted" in str(exc_info.value)


def test_replay_sorts_by_ts():
    rows = [_row("b", ts=2), _row("a", ts=1), _row("c", ts=3)]
    rl = ReplayLLM.from_ai_decisions(rows)
    seen = asyncio.run(_drain(rl))
    assert seen == ["a", "b", "c"]


async def _drain(rl: ReplayLLM):
    out = []
    try:
        while True:
            out.append(await rl.chat([]))
    except LLMError:
        return out


@dataclass
class _Row:
    raw_response: str
    ts: int = 0


def _row(raw: str, ts: int = 0) -> _Row:
    return _Row(raw_response=raw, ts=ts)


def _decision_row(raw_dict: dict, ts: int) -> _Row:
    """Build a row from a JSON dict payload (matches AIDecision.raw_response)."""
    return _Row(raw_response=json.dumps(raw_dict), ts=ts)


# ----- HistoricalBroker -------------------------------------------------------


def _fake_klines(n: int) -> list:
    """n hourly candles with rising close prices."""
    return [
        [i * 3600_000, 100 + i, 100 + i, 100 + i, 100 + i, 10]
        for i in range(n)
    ]


def _fake_symbol_info() -> dict:
    return {
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.00001000"},
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "10.00000000"},
        ]
    }


def test_broker_returns_klines_up_to_cursor_only():
    """get_klines at cursor N returns K-lines [0..N], not [0..end]."""
    klines = _fake_klines(10)
    b = HistoricalBroker(klines_by_symbol={"BTCUSDT": klines},
                         symbol_info={"BTCUSDT": _fake_symbol_info()},
                         cursor_idx=5)
    out = b.get_klines("BTCUSDT", "1h", limit=100)
    assert len(out) == 6  # candles 0..5 inclusive


def test_broker_fill_updates_ledger():
    b = HistoricalBroker(
        klines_by_symbol={"BTCUSDT": _fake_klines(5)},
        symbol_info={"BTCUSDT": _fake_symbol_info()},
        initial_cash_usdt=1000.0,
    )
    b.advance()
    b.place_order("BTCUSDT", "BUY", "limit", quantity=1.0, price=100.0)
    assert b.ledger.cash_usdt == pytest.approx(900.0)
    assert b.ledger.base_qty["BTCUSDT"] == pytest.approx(1.0)

    b.place_order("BTCUSDT", "SELL", "limit", quantity=1.0, price=110.0)
    assert b.ledger.cash_usdt == pytest.approx(1010.0)
    assert b.ledger.base_qty["BTCUSDT"] == pytest.approx(0.0)


def test_broker_account_info_reflects_ledger():
    b = HistoricalBroker(
        klines_by_symbol={"BTCUSDT": _fake_klines(5)},
        symbol_info={"BTCUSDT": _fake_symbol_info()},
        initial_cash_usdt=500.0,
    )
    b.advance()
    b.place_order("BTCUSDT", "BUY", "limit", quantity=0.5, price=100.0)
    info = b.get_account_info()
    balances = {x["asset"]: float(x["free"]) for x in info["balances"]}
    assert balances["USDT"] == pytest.approx(450.0)
    assert balances["BTCUSDT"] == pytest.approx(0.5)


# ----- metrics ---------------------------------------------------------------


def test_sharpe_zero_for_constant_equity():
    """No movement → zero variance → Sharpe is 0 (avoid div-by-zero)."""
    assert sharpe_ratio([100.0, 100.0, 100.0, 100.0]) == 0.0


def test_sharpe_positive_for_monotonic_growth():
    assert sharpe_ratio([100.0, 101.0, 102.0, 103.0]) > 0


def test_max_drawdown_tracks_peak_to_trough():
    """Equity rises 100→110→90→95. Peak=110, trough=90, DD=20."""
    dd = max_drawdown([100.0, 105.0, 110.0, 95.0, 90.0, 95.0, 100.0])
    assert dd == pytest.approx(20.0)


def test_max_drawdown_zero_for_monotonic_growth():
    assert max_drawdown([100.0, 101.0, 102.0]) == 0.0


def test_win_rate_counts_only_closed_sells():
    """Two sells: one profitable, one not. Win rate = 1/2 = 50%.

    Setup: BUY @100, BUY @100, SELL @110 (win), SELL @95 (loss).
    Average cost = 100. First sell above avg → win. Second below → loss.
    """
    fills = [
        {"ts_idx": 0, "symbol": "X", "side": "BUY", "qty": 1, "price": 100.0},
        {"ts_idx": 1, "symbol": "X", "side": "BUY", "qty": 1, "price": 100.0},
        {"ts_idx": 2, "symbol": "X", "side": "SELL", "qty": 1, "price": 110.0},
        {"ts_idx": 3, "symbol": "X", "side": "SELL", "qty": 1, "price": 95.0},
    ]
    assert win_rate(fills) == pytest.approx(0.5)


def test_summarise_returns_equity_curve_and_metrics():
    fills = [
        {"ts_idx": 0, "symbol": "X", "side": "BUY", "qty": 1, "price": 100.0},
        {"ts_idx": 1, "symbol": "X", "side": "SELL", "qty": 1, "price": 110.0},
    ]
    s = summarise(fills, initial_cash=1000.0)
    assert s["final_equity_usdt"] == pytest.approx(1010.0)
    assert s["total_return_pct"] == pytest.approx(1.0)
    assert s["n_fills"] == 2
    assert s["n_sells"] == 1
    assert s["max_drawdown_usdt"] >= 0.0


# ----- report ---------------------------------------------------------------


def test_render_report_is_valid_html_with_metrics():
    s = summarise([
        {"ts_idx": 0, "symbol": "X", "side": "BUY", "qty": 1, "price": 100.0},
        {"ts_idx": 1, "symbol": "X", "side": "SELL", "qty": 1, "price": 110.0},
    ], initial_cash=1000.0)
    html = render_report(summary=s, fills=[], title="T", period_label="1y")
    assert html.startswith("<!doctype html>")
    assert "Final equity" in html
    assert "Sharpe" in html
    assert "1010" in html


def test_render_report_contains_equity_curve_block():
    s = summarise([
        {"ts_idx": i, "symbol": "X", "side": "BUY", "qty": 1, "price": 100.0 + i}
        for i in range(10)
    ], initial_cash=1000.0)
    html = render_report(summary=s, fills=[], title="T", period_label="1y")
    # The equity curve ships as <pre> text containing block characters.
    assert "<pre>" in html
    assert "█" in html


# ----- runner end-to-end -----------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)
    yield
    Base.metadata.drop_all(engine)


def test_runner_writes_html_report(tmp_path):
    """End-to-end: feed synthetic K-lines + recorded decisions, get HTML."""
    # 5 candles for BTCUSDT.
    klines = _fake_klines(5)
    # Recorded decisions (chronologically): one buy, then one sell.
    rows = [
        _decision_row({
            "action": "buy", "symbol": "BTCUSDT", "qty": 0.1, "price": 102,
            "reason": "setup"
        }, ts=1),
        _decision_row({
            "action": "sell", "symbol": "BTCUSDT", "qty": 0.1, "price": 104,
            "reason": "take profit"
        }, ts=3),
    ]

    result = run_backtest(
        klines_by_symbol={"BTCUSDT": klines},
        symbol_info={"BTCUSDT": _fake_symbol_info()},
        ai_decision_rows=rows,
        symbols=["BTCUSDT"],
        poll_interval_steps=1,
        initial_cash_usdt=1000.0,
        report_dir=tmp_path,
    )
    assert result.report_path is not None
    assert result.report_path.exists()
    body = result.report_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in body
    assert "Final equity" in body
    # At least one fill should be recorded.
    assert result.summary["n_fills"] >= 1


def test_runner_handles_exhausted_replay(tmp_path):
    """ReplayLLM exhausted before the run finishes — runner stops cleanly."""
    klines = _fake_klines(10)
    # Only 1 recorded decision but 10 candles → exhaustion on step 1.
    rows = [
        _decision_row({
            "action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0,
            "reason": "no opportunity"
        }, ts=1),
    ]
    result = run_backtest(
        klines_by_symbol={"BTCUSDT": klines},
        symbol_info={"BTCUSDT": _fake_symbol_info()},
        ai_decision_rows=rows,
        symbols=["BTCUSDT"],
        report_dir=tmp_path,
    )
    assert result.summary["exhausted_at_step"] is not None
    # Status reset to idle after run.
    with SessionLocal() as s:
        from app.models.ai_settings import load_or_create
        assert load_or_create(s).status == "idle"


def test_runner_rejects_empty_inputs(tmp_path):
    with pytest.raises(ValueError):
        run_backtest(
            klines_by_symbol={}, symbol_info={}, ai_decision_rows=[],
            symbols=[], report_dir=tmp_path,
        )
