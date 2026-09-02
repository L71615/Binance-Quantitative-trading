"""REST endpoints for AI Trader. Spec §7.

Read-only surface (Task 11): status, decisions, dry-run.
Control endpoints (start/pause/resume/emergency-stop/reset, PUT /settings,
live-arming gate) added in Task 12.
"""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_session
from app.models.ai_decision import AIDecision
from app.models.ai_settings import load_or_create
from app.services.ai_trader.service import trader

router = APIRouter(prefix="/api/ai-trader", tags=["ai-trader"])


@router.get("/status")
def status() -> dict[str, Any]:
    return trader.status()


@router.get("/decisions")
def list_decisions(
    limit: int = Query(50, ge=1, le=500),
    symbol: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    q = session.query(AIDecision).order_by(AIDecision.ts.desc())
    if symbol:
        q = q.filter(AIDecision.symbol == symbol.upper())
    q = q.limit(limit)
    return [
        {
            "id": r.id,
            "ts": r.ts.isoformat(),
            "symbol": r.symbol,
            "action": r.action,
            "outcome": r.outcome,
            "order_id": r.order_id,
            "order_status": r.order_status,
            "filled_qty": r.filled_qty,
            "filled_price": r.filled_price,
            "error": r.error,
        }
        for r in q.all()
    ]


@router.get("/dry-run")
async def dry_run(symbol: str) -> dict[str, Any]:
    """One LLM round-trip + guard preview.

    NEVER places an order and never persists an AIDecision row.
    The brief's prose mandates returning the guards' verdict so the UI can
    distinguish "guards passed" from "guards were not run"; the brief's
    pseudocode omitted the call. Prose governs.

    The guard_verdict uses the same JSON shape as the AIDecision.guard_results
    audit column (list of {"ok": bool, "reason": str|None}), so the two
    representations match.
    """
    if not trader.llm or not trader.broker:
        raise HTTPException(503, detail="trader_not_wired")

    # Imports are local so module import does not pull in heavy deps.
    from app.services.ai_trader import context, guards, parser, prompt

    sym = symbol.upper()
    snapshot = context.gather(
        trader.broker,
        sym,
        grid_has_open_orders=trader.grid_has_open_orders,
    )
    messages = prompt.build_messages(snapshot, symbols_whitelist=[sym])
    raw = await trader.llm.chat(
        messages, response_format={"type": "json_object"}
    )
    parsed = parser.parse_response(raw, symbol_whitelist=[sym])
    if parsed is None:
        return {
            "ok": False,
            "parsed": None,
            "guard_verdict": None,
            "error": "parse_failed",
            "raw_excerpt": (raw or "")[:400],
        }

    # Run the real guards against the parsed signal. Dry-run must not place
    # an order or write an AIDecision row, so we compute pnl_today /
    # trades_today inline via the same helper _tick_symbol uses, then run
    # guards with grid_has_open_orders bound to the trader's callback.
    pnl_today, trades_today = trader._compute_today_counters()
    grid_open_cb = trader.grid_has_open_orders
    with SessionLocal() as s:
        settings = load_or_create(s)
    ok, results = guards.run_all(
        parsed,
        {
            "current_price": snapshot["price"],
            "base_balance": next(
                (float(b.get("free", 0)) for b in snapshot["balances"]
                 if b.get("asset") not in ("USDT",)),
                0.0,
            ),
        },
        settings,
        pnl_today=pnl_today,
        trades_today=trades_today,
        grid_has_open_orders=grid_open_cb,
    )
    # Same shape as AIDecision.guard_results in _tick_symbol.
    guard_verdict = [{"ok": r.ok, "reason": r.reason} for r in results]
    return {
        "ok": ok,
        "parsed": parsed,
        "guard_verdict": guard_verdict,
        "error": None,
    }


# --------------------------------------------------------------------------
# Task 12: control endpoints + live-arming gate + PUT /settings
# --------------------------------------------------------------------------


class _ConfirmBody(BaseModel):
    """Optional confirm_text body for start/reset.

    The exact-match phrase is enforced in the service layer (`start` checks
    `_LIVE_CONFIRM == confirm_text`); the router just forwards it.
    """
    confirm_text: str | None = None


class _SettingsUpdate(BaseModel):
    """PUT /settings request body.

    All fields optional (None == leave unchanged). Field-level validators
    refuse values that would defeat the guards — see the document-string
    comments on each Field for the exact rule and the rationale.
    """
    max_order_quote_usdt: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Per-order quote cap (USDT). Must be > 0 — the guard uses this as "
            "an upper bound; zero or negative makes the guard tautologically "
            "reject every order or accept unbounded ones."
        ),
    )
    max_position_per_symbol_usdt: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Per-symbol inventory cap (USDT). Must be > 0 for the same reason "
            "as max_order_quote_usdt."
        ),
    )
    daily_loss_cap_usdt: float | None = Field(
        default=None,
        lt=0,
        description=(
            "Realised daily loss cap (negative USDT). MUST be strictly < 0 — "
            "a positive value inverts the daily_loss guard so it trips on "
            "profitable days instead of losing ones."
        ),
    )
    daily_max_trades: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Daily placed-trade cap. Must be >= 1 — zero or negative makes "
            "the trade-count guard impossible to satisfy."
        ),
    )
    symbols: list[str] | None = None
    poll_interval_sec: int | None = Field(
        default=None,
        ge=1,
        description="Tick interval in seconds. Must be >= 1 to avoid busy-looping.",
    )


@router.post("/start")
async def start(body: _ConfirmBody | None = None):
    """Start the tick loop.

    If Binance testnet is False AND `armed_for_live_at` is null, refuses with
    409 `live_arming_required` until the caller retries with the exact
    confirmation string `I UNDERSTAND REAL MONEY`. The exact-match gate lives
    in the service layer (`start()` compares `_LIVE_CONFIRM == confirm_text`);
    no trimming, case-folding, or substring acceptance.
    """
    confirm = body.confirm_text if body else None
    res = await trader.start(confirm_text=confirm)
    if res.get("ok") is False and res.get("error") == "live_arming_required":
        # Spec §7 mandates the exact body shape
        # {"error":"live_arming_required",
        #  "required_confirm_text":"I UNDERSTAND REAL MONEY"}.
        # FastAPI's HTTPException wraps `detail` under {"detail": ...};
        # return a JSONResponse directly so the UI sees the documented shape.
        return JSONResponse(
            status_code=409,
            content={
                "error": "live_arming_required",
                "required_confirm_text": res["required_confirm_text"],
            },
        )
    return res


@router.post("/pause")
def pause() -> dict[str, Any]:
    trader.pause()
    return {"ok": True, "status": trader.status()["status"]}


@router.post("/resume")
def resume() -> dict[str, Any]:
    trader.resume()
    return {"ok": True, "status": trader.status()["status"]}


@router.post("/emergency-stop")
def emergency_stop() -> dict[str, Any]:
    trader.emergency_stop()
    # Status is persisted on the singleton row by the service. Subsequent
    # tick() observes status != "running" and returns before any LLM or
    # broker call — the regression test exercises this directly.
    return {"ok": True, "status": trader.status()["status"]}


@router.post("/reset")
def reset(body: _ConfirmBody | None = None) -> dict[str, Any]:
    """Reset the service to `idle`.

    Accepts from `stopped` or `error` only (the spec §3 recovery verbs).

    Live-arming gate: when `armed_for_live_at` is set, `confirm_text` must
    match `I UNDERSTAND REAL MONEY` exactly (same gate `start()` enforces
    on first-time arming). When `armed_for_live_at` is null (testnet), no
    confirmation is required — reset is just a recovery verb there.

    Refusal responses use the same body shape as `start()`'s
    `live_arming_required` refusal so one UI handler can serve both:
      409 {"error": "live_arming_required",
           "required_confirm_text": "I UNDERSTAND REAL MONEY"}.
    """
    confirm = body.confirm_text if body else None
    res = trader.reset(confirm_text=confirm)
    if res.get("ok") is False and res.get("error") == "live_arming_required":
        return JSONResponse(
            status_code=409,
            content={
                "error": "live_arming_required",
                "required_confirm_text": res["required_confirm_text"],
            },
        )
    if not res.get("ok"):
        raise HTTPException(status_code=409, detail=res.get("error"))
    return res


@router.put("/settings")
def put_settings(body: _SettingsUpdate) -> dict[str, Any]:
    """Persist user-editable risk caps + symbols + poll interval.

    Validation rules (each fires independently and returns 422):
      - max_order_quote_usdt > 0
      - max_position_per_symbol_usdt > 0
      - daily_loss_cap_usdt < 0 (negative; the guard fires when pnl_today
        drops below this floor)
      - daily_max_trades >= 1
      - poll_interval_sec >= 1
    Together these guarantee no PUT can disable a guard by inverting or
    zero-ing its threshold. All fields optional (None == leave unchanged).
    """
    with SessionLocal() as s:
        row = load_or_create(s)
        if body.max_order_quote_usdt is not None:
            row.max_order_quote_usdt = float(body.max_order_quote_usdt)
        if body.max_position_per_symbol_usdt is not None:
            row.max_position_per_symbol_usdt = float(body.max_position_per_symbol_usdt)
        if body.daily_loss_cap_usdt is not None:
            row.daily_loss_cap_usdt = float(body.daily_loss_cap_usdt)
        if body.daily_max_trades is not None:
            row.daily_max_trades = int(body.daily_max_trades)
        if body.symbols is not None:
            # Upper-case + dedupe + preserve caller order. Sorting would
            # silently rewrite a UI-provided order, which is surprising.
            seen: set[str] = set()
            normalised: list[str] = []
            for sym in body.symbols:
                u = sym.upper()
                if u not in seen:
                    seen.add(u)
                    normalised.append(u)
            row.symbol_list = normalised
        if body.poll_interval_sec is not None:
            row.poll_interval_sec = int(body.poll_interval_sec)
        row.updated_at = datetime.now(UTC)
        s.commit()
    return {"ok": True}