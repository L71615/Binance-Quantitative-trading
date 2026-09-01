"""REST endpoints for AI Trader. Spec §7.

Read-only surface (Task 11): status, decisions, dry-run.
Control endpoints (start/pause/resume/...) live in Task 12.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.ai_decision import AIDecision
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
    """One LLM round-trip. NEVER places an order; never writes a decision row."""
    if not trader.llm or not trader.broker:
        raise HTTPException(503, detail="trader_not_wired")

    # Imports are local so module import does not pull in heavy deps.
    from app.services.ai_trader import context, parser, prompt

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
    return {"ok": True, "parsed": parsed, "guard_verdict": None, "error": None}