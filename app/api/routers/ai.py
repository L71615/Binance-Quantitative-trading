"""HTTP routes for LLM-backed AI features.

`/api/ai/config` reports whether the LLM is configured (no secrets leaked).
`/api/ai/analyze` runs a single-shot market analysis on a symbol.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.llm import LLMClient, LLMError, analyze_market

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/config")
def ai_config():
    c = LLMClient()
    configured = c.is_configured()
    return {
        "configured": configured,
        "model": c.model if configured else None,
        "base_url": c.base_url if configured else None,
    }


class AnalyzeRequest(BaseModel):
    symbol: str
    klines_summary: str


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        text = await analyze_market(req.symbol, req.klines_summary)
        return {"ok": True, "analysis": text}
    except LLMError as e:
        return {"ok": False, "error": str(e), "provider": e.provider}