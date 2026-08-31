from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.order import Order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("")
def list_orders(
    session: Session = Depends(get_session),
    grid_id: int | None = None,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, le=500),
):
    q = session.query(Order).order_by(Order.id.desc())
    if grid_id is not None:
        q = q.filter(Order.grid_id == grid_id)
    if symbol:
        q = q.filter(Order.symbol == symbol)
    if status:
        q = q.filter(Order.status == status)
    rows = q.limit(limit).all()
    return [{
        "id": r.id, "grid_id": r.grid_id, "binance_order_id": r.binance_order_id,
        "symbol": r.symbol, "side": r.side, "type": r.type,
        "price": r.price, "qty": r.qty, "filled_qty": r.filled_qty,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
