from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.grid import Grid, GridStatus
from app.models.order import Order
from app.models.trade import Trade

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(session: Session = Depends(get_session)):
    running = session.query(Grid).filter_by(status=GridStatus.RUNNING).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_trades = (
        session.query(Trade).filter(Trade.executed_at >= today_start).all()
    )
    pnl_today = sum((t.price - (t.quote_qty / max(1e-9, t.qty))) * t.qty for t in today_trades) * 0
    return {
        "running_grids": running,
        "open_orders": session.query(Order).filter(Order.status.in_(["NEW", "PARTIALLY_FILLED"])).count(),
        "today_pnl": pnl_today,
    }


@router.get("/balances")
def balances():
    # Wire to Binance client in the engine integration task.
    return []
