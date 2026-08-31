from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_get_settings_strips_key_and_secret():
    _reset()
    r = client.post("/api/setup/complete", json={"acknowledged": True})
    assert r.status_code == 200
    r = client.put("/api/settings", json={"binance_testnet": True, "binance_api_key": "abc", "binance_api_secret": "xyz"})
    assert r.status_code == 200
    r = client.get("/api/settings")
    j = r.json()
    assert j["binance_testnet"] is True
    assert j["has_api_key"] is True
    assert j["has_api_secret"] is True
    assert "binance_api_key" not in j
    assert "binance_api_secret" not in j