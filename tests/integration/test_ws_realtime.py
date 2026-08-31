import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.ws.realtime import manager

client = TestClient(app)


@pytest.mark.asyncio
async def test_ws_connects_and_receives_broadcast():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with client.websocket_connect("/ws/realtime") as ws:
        await manager.broadcast({"type": "ping", "payload": {}})
        msg = ws.receive_json()
        assert msg["type"] == "ping"
