import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import Base, engine
from app.main import app

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ai_config_when_blank():
    _reset()
    r = client.get("/api/ai/config")
    assert r.status_code == 200
    j = r.json()
    assert j["configured"] is False
    assert j["model"] is None
    assert j["base_url"] is None


def test_ai_config_open_during_setup():
    """The setup wizard should be able to call /api/ai/config before setup completes."""
    _reset()
    # No setup completion — endpoint should still work because it's in OPEN_PREFIXES.
    r = client.get("/api/ai/config")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_ai_analyze_not_configured():
    _reset()
    # /api/ai/analyze is gated by setup; complete setup first.
    assert client.post("/api/setup/complete", json={"acknowledged": True}).status_code == 200
    r = client.post(
        "/api/ai/analyze",
        json={"symbol": "BTCUSDT", "klines_summary": "5m: +1% over 20 bars"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False
    assert "not configured" in j["error"].lower()
    assert j["provider"] == "openai-compatible"


def test_ai_analyze_validates_request():
    _reset()
    # /api/ai/analyze is gated by setup; complete setup first.
    assert client.post("/api/setup/complete", json={"acknowledged": True}).status_code == 200
    # Missing required fields -> 422 from pydantic validation
    r = client.post("/api/ai/analyze", json={"symbol": "BTCUSDT"})
    assert r.status_code == 422