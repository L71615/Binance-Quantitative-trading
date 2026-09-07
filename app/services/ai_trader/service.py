"""AI Trader service: state machine + tick loop. Pairs with binance.py + llm.py."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, UTC
from typing import Any, Callable

from app.db import SessionLocal
from app.models.ai_settings import AISettings, load_or_create


def _get_logger() -> logging.Logger:
    """Lazy logger accessor. Importing logging at module top is fine, but
    the test suite disables propagation before this module loads in some
    paths — going through getLogger each call ensures we get the live
    configured root logger."""
    return logging.getLogger("app.ai_trader")

# The Order table is the system of record for any order the GridTrader
# leaves resting on the exchange (see `app/api/routers/dashboard.py` which
# already reports `status in ("NEW", "PARTIALLY_FILLED")` as the canonical
# open-orders signal). Guard 6 (`symbol_exclusive`) reads from this table so
# the AI Trader refuses to add exposure to a symbol the grid is currently
# holding. The literal "NEW" is the right value because `Order.status` is a
# plain `String` column (not a Python enum) whose default IS the string
# `"NEW"`. We intentionally keep the string literal here rather than
# importing an enum — the column type does not warrant one, and the comment
# above pins the choice so a future enum-introduction will not silently
# change Guard 6's semantics.
_OPEN_ORDER_STATUS = "NEW"


def _default_grid_has_open_orders(symbol: str) -> bool:
    """Production default for Guard 6 (`symbol_exclusive`).

    Opens a short-lived session and asks the Order table whether any row
    exists for this symbol still resting on the exchange. `first()` short
    circuits as soon as a single row is found, so this stays O(1) over the
    common case. We don't cache across calls — placing one Order query per
    guard invocation is cheaper than the complexity of staleness, and the
    guard runs at most once per symbol per tick.
    """
    from app.models.order import Order
    with SessionLocal() as s:
        return (
            s.query(Order)
            .filter(Order.symbol == symbol, Order.status == _OPEN_ORDER_STATUS)
            .first()
            is not None
        )


_LIVE_CONFIRM = "I UNDERSTAND REAL MONEY"

def _is_live_mode() -> bool:
    # Lazy import to avoid hard dependency at import time (tests may not have
    # .env seeded).
    try:
        from app.config import get_settings
        return not bool(get_settings().binance_testnet)
    except Exception:
        return False


def _live_confirm_refusal(armed_for_live_at, confirm_text):
    """Standard live-arming refusal builder.

    Used by `reset()` when the service IS armed for live: any call without the
    exact `_LIVE_CONFIRM` phrase is refused. (For `start()` the symmetric case
    is the OPPOSITE — refusal only while NOT yet armed — so `start()` inlines
    its own gate. The check itself is one line; what is shared across the two
    endpoints is the refusal body shape, kept identical via this helper.)
    """
    return {
        "ok": False,
        "error": "live_arming_required",
        "required_confirm_text": _LIVE_CONFIRM,
    }


class AITraderService:
    def __init__(
        self,
        *,
        llm: Any | None = None,
        broker: Any | None = None,
        db_session_factory: Callable | None = None,
        grid_has_open_orders: Callable[[str], bool] | None = None,
        is_paper: bool = False,
    ):
        self.llm = llm
        self.broker = broker
        # `is_paper` partitions paper-trading audit rows from live. Required
        # so daily-loss / daily-trades counters do not bleed paper P&L into
        # the live guard budget. Default False (live); main.py flips this when
        # the user opts into paper mode. See CEO plan OV-C.
        self.is_paper = is_paper
        self._session_factory = db_session_factory or SessionLocal
        # Default Guard 6 callback queries the Order table for any open
        # order on this symbol. Tests still inject fakes via this ctor.
        self.grid_has_open_orders = (
            grid_has_open_orders or _default_grid_has_open_orders
        )

    # ---- wiring -------------------------------------------------------
    # Observability for the read-only /status surface. A failed or absent
    # wiring must surface in /status — never silently idle. The three flags
    # /status publishes are ALL derived from the two client attributes:
    #
    #     wiring_ok    == (self.broker is not None) and (self.llm is not None)
    #     broker_wired == self.broker is not None
    #     llm_wired    == self.llm is not None
    #
    # `wiring_ok` is a read-only property, not a stored bool, on purpose. A
    # stored copy has to be recomputed at every mutation site — the
    # constructor, set_broker, set_llm, main.py's lifespan exception
    # handler, and any future Task 12 control endpoint — and any site that
    # forgets it drifts out of sync with the client state. That is exactly
    # the bug this replaced: __init__ computed `broker is not None` while
    # the setters computed `broker is not None and llm is not None`, so
    # identical client state reported a different wiring_ok depending on
    # whether it arrived via the constructor or via a setter. A derived
    # property cannot drift. It also makes "force the flag independently of
    # the clients" unrepresentable, which is the correct constraint:
    # /status must describe reality, not an intention.
    @property
    def wiring_ok(self) -> bool:
        return self.broker is not None and self.llm is not None

    # Mutation entrypoints. Prefer these over direct attribute assignment:
    # they are the documented API for rewiring the singleton and keep call
    # sites honest that swapping a client changes what /status reports.
    def set_broker(self, broker: Any | None) -> None:
        self.broker = broker

    def set_llm(self, llm: Any | None) -> None:
        self.llm = llm

    # ---- status helpers -----------------------------------------------
    def _settings(self) -> AISettings:
        with self._session_factory() as s:
            return load_or_create(s)

    def _set_status(self, status: str, reason: str | None = None) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = status
            row.status_reason = reason
            row.updated_at = datetime.now(UTC)
            s.commit()

    def _compute_today_counters(self) -> tuple[float, int]:
        """Compute today's realised pnl and placed-trade count.

        Single source of truth: both `_tick_symbol` and `status()` call this.

        Filters by `self.is_paper` so paper-trading rows never feed the live
        daily counters. Without this, paper losses would silently trip the
        live `daily_loss_cap` guard (CEO plan OV-C).
        """
        from app.models.ai_decision import AIDecision
        with self._session_factory() as s:
            today_start = datetime.now(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_rows = (
                s.query(AIDecision)
                .filter(
                    AIDecision.ts >= today_start,
                    AIDecision.is_paper == self.is_paper,
                )
                .all()
            )
        # Today's realised pnl = revenue (sells) - cost (buys).
        # Only outcome=placed rows count; holds/errors don't move money.
        cost = sum(
            (r.filled_price or 0) * (r.filled_qty or 0)
            for r in today_rows
            if r.outcome == "placed" and r.action == "buy"
        )
        revenue = sum(
            (r.filled_price or 0) * (r.filled_qty or 0)
            for r in today_rows
            if r.outcome == "placed" and r.action == "sell"
        )
        pnl_today = revenue - cost
        # Rough trade count = placed outcomes (excluding holds with no_trade).
        trades_today = sum(1 for r in today_rows if r.outcome == "placed")
        return pnl_today, trades_today

    def status(self) -> dict[str, Any]:
        with self._session_factory() as s:
            row = load_or_create(s)
        pnl_today, trades_today = self._compute_today_counters()
        loss_budget_remaining = float(row.daily_loss_cap_usdt) - pnl_today
        return {
            "status": row.status,
            "status_reason": row.status_reason,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "last_tick_at": row.last_tick_at.isoformat() if row.last_tick_at else None,
            "max_order_quote_usdt": row.max_order_quote_usdt,
            "max_position_per_symbol_usdt": row.max_position_per_symbol_usdt,
            "daily_loss_cap_usdt": row.daily_loss_cap_usdt,
            "daily_max_trades": row.daily_max_trades,
            "symbols": row.symbol_list,
            "poll_interval_sec": row.poll_interval_sec,
            "armed_for_live_at": (
                row.armed_for_live_at.isoformat() if row.armed_for_live_at else None
            ),
            # Today's counters — same formula as the guards enforce.
            "pnl_today": pnl_today,
            # The counter is a CASH-FLOW proxy, not realised P&L: it sums
            # revenue(sells) - cost(buys) over today's `placed` rows and
            # does not subtract commissions (Binance spot taker ~0.1%) and
            # uses the order's price, not the eventual fill average. The
            # `pnl_basis` field pins the basis so a downstream reader can
            # not silently treat this as net realised P&L.
            "pnl_basis": "cash_flow_unadjusted_for_fees",
            "trades_today": trades_today,
            "loss_budget_remaining_usdt": loss_budget_remaining,
            # Observability of broker/LLM wiring. Always present.
            # Plain informational — does NOT hijack the tripwire-owned
            # `status` state machine (idle/running/paused/stopped/error).
            "wiring_ok": self.wiring_ok,
            "broker_wired": self.broker is not None,
            "llm_wired": self.llm is not None,
        }

    # ---- transitions ---------------------------------------------------
    async def start(self, *, confirm_text: str | None = None) -> dict:
        if _is_live_mode():
            with self._session_factory() as s:
                row = load_or_create(s)
                if row.armed_for_live_at is None:
                    if confirm_text != _LIVE_CONFIRM:
                        return {
                            "ok": False,
                            "error": "live_arming_required",
                            "required_confirm_text": _LIVE_CONFIRM,
                        }
                    row.armed_for_live_at = datetime.now(UTC)
                    # First-time live: conservative caps.
                    row.max_order_quote_usdt = min(
                        row.max_order_quote_usdt, 20.0
                    )
                    row.max_position_per_symbol_usdt = min(
                        row.max_position_per_symbol_usdt, 200.0
                    )
                    row.daily_loss_cap_usdt = max(row.daily_loss_cap_usdt, -10.0)
                    row.daily_max_trades = min(row.daily_max_trades, 10)
                    s.commit()
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = "running"
            row.enabled = True
            if row.started_at is None:
                row.started_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            s.commit()
        return {"ok": True, "status": "running"}

    # sync wrapper for tests / sync callers
    def start_sync(self, **kw) -> dict:
        return asyncio.run(self.start(**kw))

    def pause(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status == "running":
                row.status = "paused"
                row.updated_at = datetime.now(UTC)
                s.commit()

    def resume(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status in {"paused", "error"}:
                row.status = "running"
                row.status_reason = None
                row.updated_at = datetime.now(UTC)
                s.commit()

    def emergency_stop(self) -> None:
        with self._session_factory() as s:
            row = load_or_create(s)
            row.status = "stopped"
            row.status_reason = "emergency_stopped"
            row.updated_at = datetime.now(UTC)
            s.commit()

    def reset(self, *, confirm_text: str | None = None) -> dict:
        # Spec §3 state diagram: reset() recovers from BOTH stopped and error.
        # Task 10's tripwires can land the service in `error` after 5
        # consecutive LLM failures, and without accepting `error` here that
        # state was only recoverable by hand-editing the database.
        #
        # Live-arming gate (asymmetric with `start()`):
        # - `start()` refuses when NOT yet armed and caller didn't supply the
        #   exact phrase — that's the first-time arming flow.
        # - `reset()` refuses when ALREADY armed and caller didn't supply the
        #   exact phrase — because in that state reset is the step that puts a
        #   real-money-capable service back within one `start` of trading.
        # When `armed_for_live_at` is null (testnet) reset needs no
        # confirmation: clear from a transient upstream blip should not force
        # an operator to retype the real-money incantation. Refusing from any
        # other state (running, paused, idle) keeps `reset` a recovery verb,
        # not a free teleport.
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status not in {"stopped", "error"}:
                return {"ok": False, "error": "not_stopped"}
            if row.armed_for_live_at is not None and confirm_text != _LIVE_CONFIRM:
                return _live_confirm_refusal(row.armed_for_live_at, confirm_text)
            row.status = "idle"
            row.status_reason = None
            # Reset the consecutive LLM error counter on recovery so a fresh
            # error trip requires a new streak of 5.
            row.consecutive_llm_errors = 0
            row.updated_at = datetime.now(UTC)
            s.commit()
        return {"ok": True, "status": "idle"}

    # ---- tick loop (Task 8: context -> prompt -> llm -> parser -> guards -> audit) ----
    async def tick(self) -> None:
        from app.services.ai_trader import context, guards, parser, prompt
        from app.trace import bind_trace

        # Bind a trace_id for the entire tick so every log line / audit row
        # / guard decision can be reconstructed later by grepping one id.
        # contextvar ensures asyncio.create_task children inherit it.
        with bind_trace() as trace_id:
            logger = _get_logger()
            logger.info("tick.start", extra={"is_paper": self.is_paper})

            with self._session_factory() as s:
                row = load_or_create(s)
                if row.status != "running":
                    logger.info("tick.skip status=%s", row.status,
                                extra={"status": row.status})
                    return
                symbols = list(row.symbol_list)
                row.last_tick_at = datetime.now(UTC)
                row.updated_at = datetime.now(UTC)
                s.commit()

            logger.info("tick.symbols", extra={"symbols": symbols,
                                               "count": len(symbols)})

            # Snapshot of today's outcome stats — used by guards 4/5.
            # Single source of truth; /status uses the same helper.
            pnl_today, trades_today = self._compute_today_counters()

            for symbol in symbols:
                try:
                    await self._tick_symbol(
                        symbol,
                        pnl_today=pnl_today,
                        trades_today=trades_today,
                    )
                except Exception:
                    # One symbol's tick must not stop the others. tick()
                    # is wrapped in scheduler-side recovery too, but we
                    # also catch here so a bug in one symbol doesn't take
                    # out the rest of the poll batch.
                    logger.exception("tick.symbol_failed",
                                     extra={"symbol": symbol})

            logger.info("tick.end", extra={"pnl_today": pnl_today,
                                           "trades_today": trades_today,
                                           "trace_id": trace_id})

    async def _tick_symbol(
        self, symbol: str, *, pnl_today: float, trades_today: int
    ) -> None:
        from app.services.ai_trader import context, guards, parser, prompt

        if not self.broker or not self.llm:
            return  # service not fully wired

        grid_open_cb = self.grid_has_open_orders

        # Load market_type + leverage once per tick so all downstream calls agree.
        with self._session_factory() as s:
            row = load_or_create(s)
            market_type = row.market_type
            leverage = row.leverage

        snapshot = context.gather(
            self.broker, symbol,
            grid_has_open_orders=grid_open_cb,
            market_type=market_type,
        )
        messages = prompt.build_messages(
            snapshot,
            symbols_whitelist=[symbol],
            market_type=market_type,
            leverage=leverage or 1,
        )

        prompt_text = "\n".join(m["content"] for m in messages)
        market_json = json.dumps({k: snapshot[k] for k in snapshot if k != "klines_summary"})[:500]

        # 1) LLM call
        try:
            raw = await self.llm.chat(
                messages, response_format={"type": "json_object"}
            )
        except Exception as e:
            guard_results_json = "[]"
            self._write_decision(
                symbol=symbol,
                market_snapshot=market_json,
                prompt=prompt_text,
                raw_response="",
                parsed=None,
                action="hold",
                guard_results=guard_results_json,
                outcome="error",
                error=f"llm_exception:{type(e).__name__}:{e}",
            )
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=True,
            )
            return

        # 2) Parse
        parsed = parser.parse_response(raw, symbol_whitelist=[symbol])

        if parsed is None:
            guard_results_json = "[]"
            self._write_decision(
                symbol=symbol,
                market_snapshot=market_json,
                prompt=prompt_text,
                raw_response=raw[:4000],
                parsed=None,
                action="hold",
                guard_results=guard_results_json,
                outcome="no_trade",
                error="parse_failed",
            )
            # Spec §5 ("解析失败或 HTTP 异常") counts parse failures toward the
            # consecutive LLM-error tripwire the same way an HTTP exception
            # does. The audit row above still carries outcome="no_trade" and
            # error="parse_failed" so operators see the cause — what changes
            # here is only whether the tripwire sees this as an LLM error.
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=True,
            )
            return

        # 3) Guards
        with self._session_factory() as s:
            row = load_or_create(s)
            settings = row

        # Fetch account_info once per tick (futures only) for margin_check.
        account_info: dict = {}
        if market_type == "futures":
            try:
                account_info = self.broker.get_account_info() or {}
            except Exception:
                account_info = {}

        ok, results = guards.run_all(
            parsed,
            {"current_price": snapshot["price"],
             "base_balance": next(
                 (float(b.get("free", 0)) for b in snapshot["balances"]
                  if b.get("asset") not in ("USDT",)),
                 0.0,
             )},
            settings,
            pnl_today=pnl_today,
            trades_today=trades_today,
            grid_has_open_orders=grid_open_cb,
            market_type=market_type,
            broker=self.broker if market_type == "futures" else None,
            account_info=account_info if market_type == "futures" else None,
        )
        guard_results_json = json.dumps(
            [{"ok": r.ok, "reason": r.reason} for r in results]
        )
        if not ok:
            self._write_decision(
                symbol=symbol,
                market_snapshot=market_json,
                prompt=prompt_text,
                raw_response=raw[:4000],
                parsed=json.dumps(parsed),
                action=parsed["action"],
                guard_results=guard_results_json,
                outcome="rejected",
            )
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=False,
            )
            return

        # 4) Place order
        if parsed["action"] == "hold":
            self._write_decision(
                symbol=symbol,
                market_snapshot=market_json,
                prompt=prompt_text,
                raw_response=raw[:4000],
                parsed=json.dumps(parsed),
                action="hold",
                guard_results=guard_results_json,
                outcome="no_trade",
            )
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=False,
            )
            return

        try:
            # Exchange precision gate: LLM emits qty/price as floats, Binance
            # rejects values that violate LOT_SIZE / PRICE_FILTER / MIN_NOTIONAL
            # with -1013 / -1019 / -1016. Without rounding the LLM has no way to
            # learn it produced a bad value (the broker raises and the audit
            # row says "place_failed:..." but the operator still has to debug
            # it by hand). Round before we send, reject sub-MIN_NOTIONAL
            # without ever calling place_order, and persist the ROUNDED values
            # so what the operator sees in the audit row matches what Binance
            # actually saw.
            qty_raw = float(parsed["qty"])
            price_raw = float(parsed["price"])
            rounded = self._apply_exchange_precision(symbol, qty_raw, price_raw)
            if rounded is None:
                self._write_decision(
                    symbol=symbol,
                    market_snapshot=market_json,
                    prompt=prompt_text,
                    raw_response=raw[:4000],
                    parsed=json.dumps(parsed),
                    action=parsed["action"],
                    guard_results=guard_results_json,
                    outcome="rejected",
                    error=(
                        f"below_min_notional:"
                        f"{qty_raw * price_raw:.8f}"
                    ),
                )
                self._maybe_trip_after_tick(
                    guard_results_json=guard_results_json,
                    llm_error=False,
                )
                return
            qty, price = rounded
            order = self.broker.place_order(
                symbol=symbol,
                side=parsed["action"],
                type_="limit",
                quantity=qty,
                price=price,
            )
        except Exception as e:
            self._write_decision(
                symbol=symbol,
                market_snapshot=market_json,
                prompt=prompt_text,
                raw_response=raw[:4000],
                parsed=json.dumps(parsed),
                action=parsed["action"],
                guard_results=guard_results_json,
                outcome="error",
                error=f"place_failed:{type(e).__name__}:{e}",
            )
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=False,
            )
            return

        self._write_decision(
            symbol=symbol,
            market_snapshot=market_json,
            prompt=prompt_text,
            raw_response=raw[:4000],
            # Persist the rounded values, not the raw LLM values, so the
            # operator's view of the order matches Binance's.
            parsed=json.dumps(
                {**parsed, "qty": qty, "price": price}
            ),
            action=parsed["action"],
            guard_results=guard_results_json,
            outcome="placed",
            order_id=str(order.get("orderId")),
            order_status=order.get("status"),
            filled_qty=float(order.get("executedQty") or 0) or None,
            filled_price=float(order.get("price") or 0) or None,
        )
        self._maybe_trip_after_tick(
            guard_results_json=guard_results_json,
            llm_error=False,
        )

    def _write_decision(self, **kw) -> None:
        # Stamp is_paper from the service instance so call sites don't need to
        # remember to pass it. CEO plan OV-C: paper P&L must be partitioned
        # from live at the audit-row level so the daily counters stay clean.
        kw.setdefault("is_paper", self.is_paper)
        # market_type + leverage are read from settings once per tick and
        # passed explicitly. Defaults preserve the call shape for any test
        # that doesn't supply them.
        kw.setdefault("market_type", "spot")
        kw.setdefault("leverage", None)
        from app.models.ai_decision import AIDecision
        with self._session_factory() as s:
            s.add(AIDecision(**kw))
            s.commit()

    def _maybe_trip_after_tick(
        self,
        guard_results_json: str,
        llm_error: bool,
    ) -> None:
        """Evaluate tripwires at end of a symbol's tick.

        - 5 consecutive LLM errors → status=error.
        - daily_loss_cap_hit or daily_trades_cap_hit in guard_results_json → status=paused.
        Resets consecutive count to 0 on any successful (non-error) tick.
        """
        with self._session_factory() as s:
            row = load_or_create(s)
            # Consecutive LLM error count
            if llm_error:
                row.consecutive_llm_errors = (
                    getattr(row, "consecutive_llm_errors", 0) + 1
                )
            else:
                row.consecutive_llm_errors = 0

            tripped = False
            reason: str | None = None
            if row.consecutive_llm_errors >= 5:
                tripped = True
                reason = f"consecutive_llm_errors:{row.consecutive_llm_errors}"
            elif "daily_loss_cap_hit" in (guard_results_json or ""):
                tripped = True
                reason = "daily_loss_cap_hit"
            elif "daily_trades_cap_hit" in (guard_results_json or ""):
                tripped = True
                reason = "daily_trades_cap_hit"

            if tripped:
                new_status = "error" if "consecutive" in (reason or "") else "paused"
                row.status = new_status
                row.status_reason = reason
            row.updated_at = datetime.now(UTC)
            s.commit()

    def _apply_exchange_precision(
        self, symbol: str, qty: float, price: float,
    ) -> tuple[float, float] | None:
        """Round `qty` / `price` to the exchange's LOT_SIZE / PRICE_FILTER
        step, then enforce MIN_NOTIONAL.

        Returns the (rounded_qty, rounded_price) tuple to feed into
        `place_order`, or None if the resulting notional is below
        `MIN_NOTIONAL` (in which case the caller must write a `rejected`
        audit row and skip `place_order`).

        If the broker doesn't expose `get_symbol_info` (e.g. lightweight
        test fakes), we trust the input and return it as-is. BinanceClient
        does, and `BinanceClient.get_symbol_info` already hits
        `/api/v3/exchangeInfo`. The dry-run path never reaches here — its
        broker stub has no place_order to invoke.
        """
        get_info = getattr(self.broker, "get_symbol_info", None)
        if get_info is None:
            # No precision info available — pass through. The per-order cap
            # guard has already bounded the notional, and tests inject fakes
            # here on purpose to keep this code unit-testable without a
            # network round-trip.
            return qty, price
        info = get_info(symbol)
        step = self._filter_step(info, "LOT_SIZE", "stepSize")
        tick = self._filter_step(info, "PRICE_FILTER", "tickSize")
        min_notional = self._filter_step(info, "MIN_NOTIONAL", "minNotional")
        qty_r = _round_down_to_step(qty, step)
        price_r = _round_to_step(price, tick)
        if min_notional and qty_r * price_r < min_notional:
            return None
        return qty_r, price_r

    @staticmethod
    def _filter_step(info: Any, filter_type: str, field: str) -> float:
        """Pull a step/tick/min value out of Binance's `exchangeInfo.symbols`
        structure. Returns 0 when the filter is absent — meaning "no
        constraint" — so the caller can apply its own guard.
        """
        try:
            for f in info.get("filters", []):
                if f.get("filterType") == filter_type:
                    val = float(f.get(field, 0) or 0)
                    return val
        except (AttributeError, TypeError, ValueError):
            return 0.0
        return 0.0


def _round_down_to_step(value: float, step: float) -> float:
    """Round `value` DOWN to the nearest multiple of `step`.

    Down-rounding qty matters: rounding up could oversize the order and
    breach the per-order cap or the per-symbol position cap. Binance's
    LOT_SIZE rejects the next-larger-up multiple with -1013.
    """
    if step <= 0:
        return value
    n = int(value / step)
    return round(n * step, 12)


def _round_to_step(value: float, step: float) -> float:
    """Round `value` to the nearest multiple of `step` (any direction).

    PRICE_FILTER's tickSize is a presentation constraint, not a direction
    constraint — round-half-to-nearest is fine. We deliberately do NOT
    floor or ceil here.
    """
    if step <= 0:
        return value
    return round(round(value / step) * step, 12)


# Singleton used by the FastAPI router and by the lifespan loop.
# Default wiring: no LLM, no broker. main.py replaces these during startup
# if credentials are present. Importing this module must never fail just
# because the keyring is empty.
trader = AITraderService()
