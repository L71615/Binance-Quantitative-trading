from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.symbol import Symbol

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("")
def list_symbols(session: Session = Depends(get_session)):
    rows = session.query(Symbol).order_by(Symbol.symbol).all()
    return [{
        "symbol": r.symbol, "base": r.base, "quote": r.quote,
        "min_qty": r.min_qty, "tick_size": r.tick_size,
        "step_size": r.step_size, "min_notional": r.min_notional,
    } for r in rows]