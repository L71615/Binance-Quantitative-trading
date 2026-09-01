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


# -- Task 8: full tick loop (context -> prompt -> llm -> parser -> guards -> audit) -----
import json

from app.db import SessionLocal
from app.models.ai_decision import AIDecision


@pytest.fixture
def _fresh_state():
    """Reset ai_decision rows + revert ai_settings to defaults (idle)."""
    with SessionLocal() as s:
        s.query(AIDecision).delete()
        from app.models.ai_settings import AISettings, load_or_create
        row = load_or_create(s)
        row.status = "idle"
        row.status_reason = None
        row.last_tick_at = None
        row.symbols = '["BTCUSDT"]'
        s.commit()
    yield


class FakeLLM:
    """Returns a queue of canned responses, then a default hold."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def chat(self, messages, **kw):
        self.calls += 1
        if not self._responses:
            return json.dumps({"action": "hold", "symbol": "BTCUSDT",
                               "qty": 0, "price": 0, "reason": "queue empty"})
        return self._responses.pop(0)


class FakeBroker:
    def get_klines(self, symbol, interval, limit):
        return [[0, "60000", "60100", "59900", "60050", "10"]] * 5

    def get_account_info(self):
        return {"balances": [{"asset": "BTC", "free": "0.005", "locked": "0.001"}]}

    def get_open_orders(self, symbol=None):
        return []


@pytest.mark.asyncio
async def test_tick_skip_when_not_running(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(llm=FakeLLM([]), broker=FakeBroker())
    await s.tick()  # status is idle
    with SessionLocal() as db:
        n = db.query(AIDecision).count()
    assert n == 0


@pytest.mark.asyncio
async def test_tick_writes_decision_row_on_hold(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(
        llm=FakeLLM([json.dumps(
            {"action": "hold", "symbol": "BTCUSDT", "qty": 0, "price": 0,
             "reason": "no setup right now"})]),
        broker=FakeBroker(),
    )
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].action == "hold"
    assert rows[0].outcome == "no_trade"


@pytest.mark.asyncio
async def test_tick_records_parse_failure_on_malformed_json(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS
    s = _ATS(
        llm=FakeLLM(["not json at all"]),
        broker=FakeBroker(),
    )
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "no_trade"
    assert "parse_failed" in (rows[0].error or "")


@pytest.mark.asyncio
async def test_tick_marks_error_on_llm_exception(_fresh_state):
    from app.services.ai_trader.service import AITraderService as _ATS

    class BoomLLM:
        async def chat(self, *a, **k):
            raise RuntimeError("upstream down")

    s = _ATS(llm=BoomLLM(), broker=FakeBroker())
    s._set_status("running")
    await s.tick()
    with SessionLocal() as db:
        rows = db.query(AIDecision).all()
    assert len(rows) == 1
    assert rows[0].outcome == "error"
    assert "upstream down" in (rows[0].error or "")
