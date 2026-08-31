from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.trade import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
def list_trades(
    session: Session = Depends(get_session),
    grid_id: int | None = None,
    limit: int = Query(default=100, le=500),
):
    q = session.query(Trade).order_by(Trade.id.desc())
    if grid_id is not None:
        q = q.filter(Trade.grid_id == grid_id)
    rows = q.limit(limit).all()
    return [{
        "id": r.id, "grid_id": r.grid_id, "order_id": r.order_id,
        "price": r.price, "qty": r.qty, "quote_qty": r.quote_qty,
        "fee": r.fee, "fee_asset": r.fee_asset,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
    } for r in rows]
