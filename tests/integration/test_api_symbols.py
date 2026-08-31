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


def test_symbols_lists_what_we_have():
    _reset()  # helper from prior test file
    r = client.get("/api/symbols")
    assert r.status_code == 200
    rows = r.json()
    # Only what we inserted
    assert any(s["symbol"] == "BTCUSDT" for s in rows)