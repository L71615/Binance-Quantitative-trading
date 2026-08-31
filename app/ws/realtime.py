"""WebSocket ConnectionManager — fans out events to all connected clients."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast_threadsafe_from_sync(self, loop: asyncio.AbstractEventLoop, message: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)


manager = ConnectionManager()
