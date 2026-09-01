"""REST endpoints for AI Trader. Spec §7.

Read-only surface (Task 11): status, decisions, dry-run.
Control endpoints (start/pause/resume/...) live in Task 12.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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