"""HistoricalBroker: deterministic Broker backed by recorded K-line data.

CEO plan P0-5: backtest needs a Broker that satisfies the same interface
as BinanceClient (so tick() does not care which one is wired) but answers
from a frozen historical dataset instead of the network.

The interface satisfied:
    get_klines(symbol, interval, limit=500) -> list
    get_account_info() -> dict (balances tracked from fills)
    get_open_orders(symbol=None) -> list (always empty — backtest is fill-now)
    place_order(symbol, side, type_, quantity, price) -> dict
    get_symbol_info(symbol) -> dict (frozen from a snapshot)
    cancel_order, get_all_orders: not used by tick()

`place_order` is the heart of the simulator. We fill immediately at the
requested price (no queue, no partial fill) — backtest is a thin slice
of reality and we pick the most forgiving model that still has teeth.
A more sophisticated fill model (queue position, slippage based on
volatility, latency) belongs in a v2 if it ever becomes the bottleneck
between the operator and a real-money decision.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ledger:
    """Per-symbol position + cash. Updated by `place_order`."""
    cash_usdt: float = 0.0
    base_qty: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def apply_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        if side.upper() == "BUY":
            self.cash_usdt -= qty * price
            self.base_qty[symbol] += qty
        else:  # SELL
            self.cash_usdt += qty * price
            self.base_qty[symbol] -= qty


class HistoricalBroker:
    """Frozen dataset answerer. Constructed once per backtest run."""

    def __init__(
        self,
        *,
        klines_by_symbol: dict[str, list[list]],
        symbol_info: dict[str, dict],
        initial_cash_usdt: float = 10_000.0,
        cursor_idx: int = 0,
    ):
        # klines_by_symbol: {symbol: [[ts, o, h, l, c, v, ...], ...]}
        # symbol_info:    {symbol: exchangeInfo-symbols entry}
        self._klines = klines_by_symbol
        self._info = symbol_info
        self._cursor = cursor_idx  # advances as backtest walks forward
        self.ledger = Ledger(cash_usdt=initial_cash_usdt)

        # Audit trail of fills. Persisted to backtest_report.html later.
        self.fills: list[dict[str, Any]] = []
        # Order-id mint. Mirrors BinanceClient's behavior so audit code
        # downstream does not need to special-case.
        self._next_order_id = 1

    # ---- Broker surface ---------------------------------------------------

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> list:
        """Return the most recent `limit` K-lines UP TO the cursor.

        The cursor is what makes this "historical" — at simulation time
        `t` we return only K-lines whose open_time <= t. This is what
        prevents the backtest from peeking at future prices.
        """
        rows = self._klines.get(symbol, [])
        if not rows:
            return []
        # Find rows whose ts <= cursor position. cursor is an int index
        # into the array; for a true timestamp simulation the operator
        # can pre-slice before passing in.
        end = min(self._cursor + 1, len(rows))
        window = rows[max(0, end - limit):end]
        return window

    def get_account_info(self) -> dict:
        """Return balances derived from the ledger. No external state."""
        balances = [
            {"asset": "USDT", "free": str(self.ledger.cash_usdt),
             "locked": "0"},
        ]
        for asset, qty in self.ledger.base_qty.items():
            balances.append({"asset": asset, "free": str(qty), "locked": "0"})
        return {"balances": balances}

    def get_open_orders(self, symbol: str | None = None) -> list:
        """Backtest fills immediately; nothing is ever resting on the book."""
        return []

    def get_symbol_info(self, symbol: str) -> dict:
        info = self._info.get(symbol, {})
        if not info:
            return {"symbol": symbol, "filters": []}
        return info

    def place_order(
        self,
        symbol: str,
        side: str,
        type_: str,
        *,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
    ) -> dict:
        """Fill immediately at the requested price. Backtest is fill-now."""
        fill_price = float(price) if price is not None else 0.0
        self.ledger.apply_fill(symbol, side, quantity, fill_price)
        order_id = self._next_order_id
        self._next_order_id += 1
        self.fills.append({
            "order_id": order_id,
            "ts_idx": self._cursor,
            "symbol": symbol,
            "side": side,
            "qty": quantity,
            "price": fill_price,
            "type": type_,
        })
        # Mirrors BinanceClient's response shape (camelCase keys, strings).
        return {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": type_,
            "status": "FILLED",
            "executedQty": str(quantity),
            "price": str(fill_price),
        }

    # ---- Backtest control -----------------------------------------------

    def advance(self) -> None:
        """Move the cursor forward by one step. Called by the backtest
        runner between K-lines so subsequent get_klines returns a
        strictly larger prefix."""
        self._cursor += 1

    @property
    def cursor(self) -> int:
        return self._cursor
