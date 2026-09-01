import json
from datetime import datetime, UTC

from app.db import Base, SessionLocal, engine
from app.models.ai_decision import AIDecision
from app.models.ai_settings import AISettings, load_or_create, save


def setup_module(_):
    # Drop & recreate to avoid cross-test pollution.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_load_or_create_creates_singleton():
    with SessionLocal() as s:
        s1 = load_or_create(s)
        assert s1.id == 1
        assert s1.status == "idle"
        assert s1.max_order_quote_usdt == 50.0  # testnet default
        assert json.loads(s1.symbols) == ["BTCUSDT"]
        s.commit()


def test_symbol_list_roundtrip():
    with SessionLocal() as s:
        st = load_or_create(s)
        st.symbols = json.dumps(["BTCUSDT", "ETHUSDT"])
        s.commit()
    with SessionLocal() as s2:
        st2 = load_or_create(s2)
        assert st2.symbol_list == ["BTCUSDT", "ETHUSDT"]


def test_save_persists_and_bumps_updated_at():
    with SessionLocal() as s:
        st = load_or_create(s)
        before = st.updated_at
        st.enabled = True
        st.status = "running"
        saved = save(s, st)
        assert saved.updated_at >= before
    with SessionLocal() as s2:
        st2 = load_or_create(s2)
        assert st2.enabled is True
        assert st2.status == "running"


def test_ai_decision_persists():
    with SessionLocal() as s:
        d = AIDecision(
            ts=datetime.now(UTC),
            symbol="BTCUSDT",
            market_snapshot="{}",
            prompt="sys+usr",
            raw_response='{"action":"hold"}',
            parsed='{"action":"hold"}',
            action="hold",
            guard_results="[]",
            outcome="no_trade",
        )
        s.add(d)
        s.commit()
        s.refresh(d)
        assert d.id is not None
        assert d.action == "hold"
