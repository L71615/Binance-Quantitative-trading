from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.grid import Grid, GridStatus
from app.models.order import Order

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(symbol="BTCUSDT", lower_price=1, upper_price=2,
                 grid_count=3, grid_mode="arithmetic", total_quote_amount=10,
                 status=GridStatus.STOPPED, created_at=datetime.now(timezone.utc))
        s.add(g); s.flush()
        s.add(Order(grid_id=g.id, binance_order_id=999, symbol="BTCUSDT",
                    side="BUY", type="LIMIT", price=1.5, qty=0.001,
                    filled_qty=0, status="NEW",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)))
        s.commit()
    client.post("/api/setup/complete", json={"acknowledged": True})


def test_orders_list():
    _reset()
    r = client.get("/api/orders")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_dashboard_overview_returns_dict():
    _reset()
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 200
    j = r.json()
    assert "running_grids" in j
