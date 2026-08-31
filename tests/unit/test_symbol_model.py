from datetime import datetime, timezone

from app.db import Base, engine, SessionLocal
from app.models.symbol import Symbol


def test_roundtrip():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.add(Symbol(
            symbol="BTCUSDT", base="BTC", quote="USDT",
            min_qty=0.00001, tick_size=0.01, step_size=0.00001,
            min_notional=10.0, updated_at=now,
        ))
        s.commit()
    with SessionLocal() as s:
        row = s.get(Symbol, "BTCUSDT")
        assert row is not None
        assert row.base == "BTC"
        assert row.min_qty == 0.00001
        assert row.updated_at == now
        assert row.updated_at.tzinfo is not None
