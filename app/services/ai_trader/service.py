"""AI Trader service: state machine + tick loop. Pairs with binance.py + llm.py."""
from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, UTC
from typing import Any, Callable

from app.db import SessionLocal
from app.models.ai_settings import AISettings, load_or_create


_LIVE_CONFIRM = "I UNDERSTAND REAL MONEY"

def _is_live_mode() -> bool:
    # Lazy import to avoid hard dependency at import time (tests may not have
    # .env seeded).
    try:
        from app.config import get_settings
        return not bool(get_settings().binance_testnet)
    except Exception:
        return False


class AITraderService:
    def __init__(
        self,
        *,
        llm: Any | None = None,
        broker: Any | None = None,
        db_session_factory: Callable | None = None,
        grid_has_open_orders: Callable[[str], bool] | None = None,
    ):
        self.llm = llm
        self.broker = broker
        self._session_factory = db_session_factory or SessionLocal
        self.grid_has_open_orders = grid_has_open_orders or (lambda s: False)

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
        """
        from app.models.ai_decision import AIDecision
        with self._session_factory() as s:
            today_start = datetime.now(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_rows = (
                s.query(AIDecision)
                .filter(AIDecision.ts >= today_start)
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
        # state was only recoverable by hand-editing the database. `confirm_text`
        # is accepted but not required: the brief's `POST /reset` body has
        # `confirm_text?` (optional); the arming gate is enforced only on
        # `start`. Refusing from any other state (running, paused, idle) keeps
        # `reset` a recovery verb, not a free teleport.
        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status not in {"stopped", "error"}:
                return {"ok": False, "error": "not_stopped"}
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

        with self._session_factory() as s:
            row = load_or_create(s)
            if row.status != "running":
                return
            symbols = list(row.symbol_list)
            row.last_tick_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            s.commit()

        # Snapshot of today's outcome stats — used by guards 4/5.
        # Single source of truth; /status uses the same helper.
        pnl_today, trades_today = self._compute_today_counters()

        for symbol in symbols:
            await self._tick_symbol(
                symbol,
                pnl_today=pnl_today,
                trades_today=trades_today,
            )

    async def _tick_symbol(
        self, symbol: str, *, pnl_today: float, trades_today: int
    ) -> None:
        from app.services.ai_trader import context, guards, parser, prompt

        if not self.broker or not self.llm:
            return  # service not fully wired

        grid_open_cb = self.grid_has_open_orders
        snapshot = context.gather(self.broker, symbol, grid_has_open_orders=grid_open_cb)
        messages = prompt.build_messages(snapshot, symbols_whitelist=[symbol])

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
            self._maybe_trip_after_tick(
                guard_results_json=guard_results_json,
                llm_error=False,
            )
            return

        # 3) Guards
        with self._session_factory() as s:
            row = load_or_create(s)
            settings = row
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
            order = self.broker.place_order(
                symbol=symbol,
                side=parsed["action"],
                type_="limit",
                quantity=parsed["qty"],
                price=parsed["price"],
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
            parsed=json.dumps(parsed),
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


# Singleton used by the FastAPI router and by the lifespan loop.
# Default wiring: no LLM, no broker. main.py replaces these during startup
# if credentials are present. Importing this module must never fail just
# because the keyring is empty.
trader = AITraderService()
