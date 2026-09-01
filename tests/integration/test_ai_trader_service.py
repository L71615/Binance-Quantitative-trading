import pytest

from app.db import Base, SessionLocal, engine
from app.services.ai_trader.service import AITraderService


def setup_module(_):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_initial_status_is_idle():
    s = AITraderService()
    assert s.status()["status"] == "idle"


def test_pause_and_resume_round_trip(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: type("Cfg", (), {"binance_testnet": True})())
    s = AITraderService()
    # The actual method sync_run below
    s._set_status("running")
    s.pause()
    assert s.status()["status"] == "paused"
    s.resume()
    assert s.status()["status"] == "running"


def test_emergency_stop_from_running(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: type("Cfg", (), {"binance_testnet": True})())
    s = AITraderService()
    s._set_status("running")
    s.emergency_stop()
    assert s.status()["status"] == "stopped"


def test_reset_from_stopped_to_idle():
    s = AITraderService()
    s._set_status("stopped")
    s.reset()
    assert s.status()["status"] == "idle"


def test_tick_placeholder_updates_last_tick_at():
    import asyncio
    s = AITraderService()
    s._set_status("running")
    asyncio.run(s.tick())
    st = s.status()
    assert st["last_tick_at"] is not None
