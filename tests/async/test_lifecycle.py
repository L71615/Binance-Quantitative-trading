import asyncio

import pytest


@pytest.mark.asyncio
async def test_grid_lifecycle_runs_strategy_and_broadcasts_status():
    from app.engine.lifecycle import Lifecycle

    lc = Lifecycle()
    await lc.start()
    events = []
    lc.on_event(lambda e: events.append(e))
    await lc.start_grid(grid_id=42, symbol="BTCUSDT", lower=1.0, upper=2.0,
                        count=3, mode="arithmetic", total_quote_amount=10.0)
    await asyncio.sleep(0.1)
    await lc.stop_grid(grid_id=42)
    await lc.stop()
    types = [e["type"] for e in events]
    assert "grid_running" in types
    assert "grid_stopped" in types