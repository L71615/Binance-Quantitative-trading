from app.db import Base, engine, SessionLocal
from app.models.setting import Setting
from app.models.app_state import AppState


def _recreate():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_setting_roundtrip():
    _recreate()
    with SessionLocal() as s:
        s.add(Setting(key="binance_testnet", value="true"))
        s.commit()
    with SessionLocal() as s:
        v = s.get(Setting, "binance_testnet")
        assert v is not None
        assert v.value == "true"


def test_app_state_roundtrip():
    _recreate()
    with SessionLocal() as s:
        s.add(AppState(key="setup_completed", value="false"))
        s.commit()
    with SessionLocal() as s:
        v = s.get(AppState, "setup_completed")
        assert v.value == "false"