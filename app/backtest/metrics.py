"""Backtest metrics: Sharpe, max drawdown, equity curve, win rate.

Pure functions — no DB, no broker. Operate on a sequence of fills
(`broker.fills`) and return dicts the report writer can format.

Why this is in its own module: the runner iterates over historical
K-lines, but the metric math is independent of how those lines were
collected. Splitting keeps the runner thin (one file = one job) and
the metric math independently testable (no setup, no fixtures).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Sequence


def equity_curve(fills: Sequence[dict], initial_cash: float) -> list[dict]:
    """Walk fills in order, return [{ts_idx, equity_usdt, ...}, ...].

    Equity at any point = initial_cash + sum(buys are cost, sells are revenue).
    We treat BUY as a cash outflow and SELL as an inflow; mark-to-market of
    base_qty uses the fill's price (close enough for daily-resolution
    backtests; a v2 would revalue base_qty at the latest mid).
    """
    out: list[dict] = []
    cash = initial_cash
    base_qty: dict[str, float] = defaultdict(float)
    base_cost_basis: dict[str, float] = defaultdict(float)

    for f in fills:
        sym = f["symbol"]
        side = f["side"].upper()
        qty = float(f["qty"])
        price = float(f["price"])
        if side == "BUY":
            cash -= qty * price
            base_cost_basis[sym] += qty * price
            base_qty[sym] += qty
        else:
            cash += qty * price
            # Realised P&L on the sold portion (average-cost).
            avg = base_cost_basis[sym] / base_qty[sym] if base_qty[sym] > 0 else 0.0
            realised = (price - avg) * qty
            base_cost_basis[sym] -= avg * qty
            base_qty[sym] -= qty
            out.append({"ts_idx": f.get("ts_idx", 0), "realised_pnl": realised,
                        "side": side, "symbol": sym, "qty": qty, "price": price})
        # Mark-to-market of remaining base.
        mtm = cash + sum(base_cost_basis[s] for s in base_cost_basis)
        out.append({"ts_idx": f.get("ts_idx", 0), "equity_usdt": mtm,
                    "cash_usdt": cash})

    return out


def max_drawdown(equity_points: Sequence[float]) -> float:
    """Largest peak-to-trough decline. Returns a positive number (the
    drawdown magnitude in USDT), or 0.0 if equity never declined."""
    peak = -math.inf
    max_dd = 0.0
    for v in equity_points:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def sharpe_ratio(equity_points: Sequence[float], *, periods_per_year: int = 365 * 24) -> float:
    """Annualised Sharpe from per-period equity changes.

    Returns 0.0 if fewer than 2 points. Uses population stddev (N-1) for
    the period returns; the operator can re-run with a different model
    if their backtest needs sample stddev instead.
    """
    if len(equity_points) < 2:
        return 0.0
    returns = [equity_points[i] / equity_points[i - 1] - 1.0
               for i in range(1, len(equity_points))]
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)


def win_rate(fills: Sequence[dict]) -> float:
    """Fraction of SELL fills whose realised P&L > 0. Buys are excluded
    from numerator and denominator — they're not closed positions.

    Returns 0.0 when there are no closed positions yet.
    """
    if not fills:
        return 0.0
    # Walk through fills building realised P&L per sell.
    base_cost_basis: dict[str, float] = defaultdict(float)
    base_qty: dict[str, float] = defaultdict(float)
    wins = 0
    sells = 0
    for f in fills:
        sym = f["symbol"]
        side = f["side"].upper()
        qty = float(f["qty"])
        price = float(f["price"])
        if side == "BUY":
            base_cost_basis[sym] += qty * price
            base_qty[sym] += qty
        else:
            avg = base_cost_basis[sym] / base_qty[sym] if base_qty[sym] > 0 else 0.0
            sells += 1
            if price > avg:
                wins += 1
            base_cost_basis[sym] -= avg * qty
            base_qty[sym] -= qty
    return wins / sells if sells > 0 else 0.0


def summarise(fills: Sequence[dict], initial_cash: float) -> dict:
    """Aggregate everything the HTML report needs."""
    eq = equity_curve(fills, initial_cash)
    eq_points = [p["equity_usdt"] for p in eq if "equity_usdt" in p]
    final_equity = eq_points[-1] if eq_points else initial_cash
    return {
        "initial_cash_usdt": initial_cash,
        "final_equity_usdt": final_equity,
        "total_return_pct": (final_equity - initial_cash) / initial_cash * 100
            if initial_cash else 0.0,
        "n_fills": len(fills),
        "n_sells": sum(1 for f in fills if f["side"].upper() == "SELL"),
        "sharpe_ratio": sharpe_ratio(eq_points),
        "max_drawdown_usdt": max_drawdown(eq_points),
        "win_rate": win_rate(fills),
        "equity_curve": eq,
    }
