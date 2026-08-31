from datetime import datetime, timezone

from app.db import Base, engine, SessionLocal
from app.models.grid import Grid, GridStatus
from app.models.order import Order


def test_grid_create_and_status():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(
            symbol="BTCUSDT", lower_price=100.0, upper_price=110.0,
            grid_count=6, grid_mode="arithmetic", total_quote_amount=60.0,
            status=GridStatus.PENDING, created_at=datetime.now(timezone.utc),
        )
        s.add(g)
        s.commit()
        gid = g.id
    with SessionLocal() as s:
        g2 = s.get(Grid, gid)
        assert g2.status == GridStatus.PENDING


def test_order_links_to_grid():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(symbol="BTCUSDT", lower_price=1.0, upper_price=2.0,
                 grid_count=3, grid_mode="arithmetic",
                 total_quote_amount=10.0, status=GridStatus.PENDING,
                 created_at=datetime.now(timezone.utc))
        s.add(g)
        s.flush()
        o = Order(grid_id=g.id, binance_order_id=12345, symbol="BTCUSDT",
                  side="BUY", type="LIMIT", price=1.5, qty=0.001,
                  filled_qty=0.0, status="NEW",
                  created_at=datetime.now(timezone.utc),
                  updated_at=datetime.now(timezone.utc))
        s.add(o)
        s.commit()
    with SessionLocal() as s:
        order = s.query(Order).filter_by(binance_order_id=12345).one()
        assert order.grid_id is not None