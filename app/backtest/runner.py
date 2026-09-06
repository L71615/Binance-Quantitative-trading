"""Backtest runner: replay AIDecision against HistoricalBroker, write report.

End-to-end pipeline:
  1. Build a HistoricalBroker fed by historical K-lines.
  2. Build a ReplayLLM fed by AIDecision rows (in chronological order).
  3. Spin up an AITraderService with these two clients wired in place of
     the live broker/LLM.
  4. For each K-line step: advance the broker cursor, call tick().
  5. Collect fills + decisions, compute metrics, render HTML.

Why we don't reuse the live AITraderService.tick() as-is: tick() reads
status from the singleton settings row. Backtest bypasses the state
machine — we want every tick to run regardless of "running" status, so
we set status="running" at start and "idle" at end. We also set
is_paper=True on the backtest service so any AIDecision rows written
during the run are partitioned away from live.

Replays LLM at zero cost — the only real expense is the per-tick
parquet/SQLite read for the latest K-lines. For 365 days × hourly
resolution that's ~8,760 reads, well under a second on a local disk.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

from app.backtest.metrics import summarise
from app.backtest.report import render_report
from app.broker.historical import HistoricalBroker
from app.services.ai_trader.replay_llm import ReplayLLM
from app.services.ai_trader.service import AITraderService
from app.services.llm import LLMError

logger = logging.getLogger("app.backtest")


@dataclass
class BacktestResult:
    summary: dict
    fills: list[dict]
    decisions_logged: int
    report_path: Path | None


def run_backtest(
    *,
    klines_by_symbol: dict[str, list],
    symbol_info: dict[str, dict],
    ai_decision_rows: list,
    symbols: list[str],
    poll_interval_steps: int = 1,
    initial_cash_usdt: float = 10_000.0,
    report_dir: Path | None = None,
) -> BacktestResult:
    """Run a single backtest pass. Returns summary + fills + report path.

    Args:
      klines_by_symbol: {symbol: [[ts,o,h,l,c,v,...], ...]}
        — must share a common length so the cursor advances uniformly.
        The shortest list bounds the run length.
      symbol_info: {symbol: exchangeInfo-symbols entry} — frozen for the run.
      ai_decision_rows: AIDecision rows in any order; will be sorted by ts.
      symbols: which symbols tick() should evaluate (drives AISettings.symbols).
      poll_interval_steps: how many K-line steps between ticks. 1 = every
        candle; 24 = once per day on hourly candles.
      initial_cash_usdt: starting cash for the ledger.
      report_dir: where to write the HTML; defaults to docs/backtests/.
    """
    if not klines_by_symbol or not symbols:
        raise ValueError("klines_by_symbol and symbols are required")

    # Find the run length: shortest K-line series bounds us.
    run_length = min(len(klines_by_symbol[s]) for s in symbols)
    if run_length == 0:
        raise ValueError("klines_by_symbol contains empty series")

    broker = HistoricalBroker(
        klines_by_symbol=klines_by_symbol,
        symbol_info=symbol_info,
        initial_cash_usdt=initial_cash_usdt,
        cursor_idx=0,
    )
    replay = ReplayLLM.from_ai_decisions(ai_decision_rows)

    # Bypass the live state machine by setting status=running in settings,
    # so tick() actually evaluates decisions. is_paper=True keeps the
    # audit rows partitioned from any future live counter queries.
    from app.db import SessionLocal
    from app.models.ai_settings import load_or_create
    with SessionLocal() as s:
        row = load_or_create(s)
        row.status = "running"
        row.symbols = __import__("json").dumps(symbols)
        row.poll_interval_sec = 1  # backtest doesn't honour this anyway
        s.commit()

    svc = AITraderService(is_paper=True)
    svc.set_broker(broker)  # type: ignore[arg-type]
    svc.set_llm(replay)     # type: ignore[arg-type]

    decisions_logged = 0
    exhausted_at_step: int | None = None

    # Walk the candles. tick() reads K-lines via get_klines, so we step
    # the cursor forward between ticks.
    #
    # Why we do NOT just catch LLMError here: tick() catches LLMError
    # internally and turns it into an audit row, so the runner never
    # sees the exception. Instead we probe ReplayLLM.exhausted_at after
    # each tick — when ReplayLLM runs out of responses, that flag is
    # set and we stop the loop.
    step = 0
    while step < run_length:
        broker.advance()
        try:
            import asyncio
            asyncio.run(svc.tick())
        except Exception:
            # Tick exceptions must not crash the backtest — log and keep
            # walking so one bad decision does not lose the rest of the
            # run. The metrics report flags total steps run vs. fills so
            # the operator sees the discrepancy.
            logger.exception("tick exception at step %d", step)

        if replay.exhausted_at is not None:
            exhausted_at_step = step
            logger.info("replay exhausted at step %d (after %d responses)",
                        step, replay.exhausted_at)
            break

        step += poll_interval_steps
        decisions_logged += 1

    # Reset state so a subsequent live run isn't accidentally "running".
    with SessionLocal() as s:
        row = load_or_create(s)
        row.status = "idle"
        s.commit()

    summary = summarise(broker.fills, initial_cash_usdt)
    summary["steps_run"] = decisions_logged
    summary["exhausted_at_step"] = exhausted_at_step
    summary["symbols"] = symbols

    report_path: Path | None = None
    if report_dir is None:
        report_dir = Path("docs/backtests")
    report_dir.mkdir(parents=True, exist_ok=True)
    period = f"{len(klines_by_symbol[symbols[0]])} candles across {len(symbols)} symbols"
    if exhausted_at_step is not None:
        period += f" (exhausted at step {exhausted_at_step})"
    title = "Backtest Report"
    body = render_report(
        summary=summary,
        fills=broker.fills,
        title=title,
        period_label=period,
    )
    fname = f"backtest-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.html"
    report_path = report_dir / fname
    report_path.write_text(body, encoding="utf-8")
    logger.info("wrote report to %s", report_path)

    return BacktestResult(
        summary=summary,
        fills=broker.fills,
        decisions_logged=decisions_logged,
        report_path=report_path,
    )
