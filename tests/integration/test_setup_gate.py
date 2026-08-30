from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_setup_state_when_unconfigured():
    _reset()
    r = client.get("/api/setup/state")
    assert r.status_code == 200
    assert r.json() == {"setup_required": True}


def test_protected_endpoint_blocked_when_unconfigured():
    _reset()
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 403
    assert r.json().get("setup_required") is True


def test_setup_endpoint_open_even_when_unconfigured():
    _reset()
    r = client.get("/api/setup/state")
    assert r.status_code == 200


def test_protected_endpoint_opens_when_setup_completed():
    _reset()
    # complete setup via the endpoint
    r = client.post("/api/setup/complete", json={"acknowledged": True})
    assert r.status_code == 200
    r = client.get("/api/dashboard/overview")
    assert r.status_code != 403


def test_health_open():
    _reset()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}