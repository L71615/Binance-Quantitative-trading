from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.engine.lifecycle import lifecycle
from app.models.grid import Grid, GridStatus

router = APIRouter(prefix="/api/grids", tags=["grids"])


class GridCreate(BaseModel):
    symbol: str
    lower_price: float = Field(gt=0)
    upper_price: float = Field(gt=0)
    grid_count: int = Field(ge=2, le=200)
    grid_mode: str = Field(default="arithmetic")
    total_quote_amount: float = Field(ge=0)


def _grid_to_dict(g: Grid) -> dict:
    return {
        "id": g.id,
        "symbol": g.symbol,
        "lower_price": g.lower_price,
        "upper_price": g.upper_price,
        "grid_count": g.grid_count,
        "grid_mode": g.grid_mode,
        "total_quote_amount": g.total_quote_amount,
        "status": g.status.value if isinstance(g.status, GridStatus) else g.status,
        "error_message": g.error_message,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "started_at": g.started_at.isoformat() if g.started_at else None,
        "stopped_at": g.stopped_at.isoformat() if g.stopped_at else None,
    }


@router.post("", status_code=201)
def create_grid(payload: GridCreate, session: Session = Depends(get_session)):
    if payload.lower_price >= payload.upper_price:
        raise HTTPException(status_code=400, detail="lower must be < upper")
    g = Grid(
        symbol=payload.symbol,
        lower_price=payload.lower_price,
        upper_price=payload.upper_price,
        grid_count=payload.grid_count,
        grid_mode=payload.grid_mode,
        total_quote_amount=payload.total_quote_amount,
        status=GridStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return _grid_to_dict(g)


@router.get("")
def list_grids(session: Session = Depends(get_session)):
    return [_grid_to_dict(g) for g in session.query(Grid).order_by(Grid.id.desc()).all()]


@router.get("/{grid_id}")
def get_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404, detail="not found")
    return _grid_to_dict(g)


@router.delete("/{grid_id}", status_code=204)
def delete_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404, detail="not found")
    if g.status == GridStatus.RUNNING or g.status == GridStatus.PENDING:
        raise HTTPException(status_code=400, detail="grid must be stopped before delete")
    session.delete(g)
    session.commit()
    return None


# start/stop delegate to the Lifecycle singleton (Task 21).
@router.post("/{grid_id}/start")
def start_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404)
    g.status = GridStatus.PENDING  # engine flips to RUNNING when it actually starts
    g.started_at = datetime.now(timezone.utc)
    g.stopped_at = None
    g.error_message = None
    session.commit()
    # Hand off to the lifecycle; it will fire 'grid_running' once the
    # strategy has been wired into the engine and on_start has run.
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(
            lifecycle.start_grid(
                grid_id=grid_id, symbol=g.symbol,
                lower=g.lower_price, upper=g.upper_price,
                count=g.grid_count, mode=g.grid_mode,
                total_quote_amount=g.total_quote_amount,
            )
        )
    else:
        asyncio.run(
            lifecycle.start_grid(
                grid_id=grid_id, symbol=g.symbol,
                lower=g.lower_price, upper=g.upper_price,
                count=g.grid_count, mode=g.grid_mode,
                total_quote_amount=g.total_quote_amount,
            )
        )
    return {"ok": True, "id": grid_id}


@router.post("/{grid_id}/stop")
def stop_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404)
    g.status = GridStatus.STOPPED
    g.stopped_at = datetime.now(timezone.utc)
    session.commit()
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(lifecycle.stop_grid(grid_id=grid_id))
    else:
        asyncio.run(lifecycle.stop_grid(grid_id=grid_id))
    return {"ok": True, "id": grid_id}