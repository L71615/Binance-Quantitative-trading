from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.symbol import Symbol

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        s.add(Symbol(symbol="BTCUSDT", base="BTC", quote="USDT",
                     min_qty=0.00001, tick_size=0.01, step_size=0.00001,
                     min_notional=10.0, updated_at=datetime.now(timezone.utc)))
        s.add(Symbol(symbol="ETHUSDT", base="ETH", quote="USDT",
                     min_qty=0.0001, tick_size=0.01, step_size=0.0001,
                     min_notional=10.0, updated_at=datetime.now(timezone.utc)))
        s.commit()
    client.post("/api/setup/complete", json={"acknowledged": True})


def test_create_and_list_grid():
    _reset()
    r = client.post("/api/grids", json={
        "symbol": "BTCUSDT", "lower_price": 100.0, "upper_price": 110.0,
        "grid_count": 6, "grid_mode": "arithmetic", "total_quote_amount": 60.0,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["status"] == "pending"
    r = client.get("/api/grids")
    assert len(r.json()) == 1


def test_delete_grid_only_when_stopped():
    _reset()
    r = client.post("/api/grids", json={
        "symbol": "BTCUSDT", "lower_price": 1.0, "upper_price": 2.0,
        "grid_count": 3, "grid_mode": "arithmetic", "total_quote_amount": 10.0,
    })
    gid = r.json()["id"]
    # cannot delete pending
    d = client.delete(f"/api/grids/{gid}")
    assert d.status_code == 400