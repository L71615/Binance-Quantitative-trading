import asyncio

import pytest

from app.engine.engine import Engine


@pytest.mark.asyncio
async def test_engine_starts_and_stops_cleanly():
    eng = Engine()
    await eng.start()
    assert eng.is_running
    await eng.stop()
    assert not eng.is_running


@pytest.mark.asyncio
async def test_engine_routes_trade_to_grid():
    eng = Engine()
    await eng.start()
    fired = []

    # register a fake strategy
    eng.register_strategy(grid_id=1, strategy_name="g1", events=fired, ctx_args={})
    await eng.handle_trade_update({"grid_id": 1, "side": "BUY", "price": 100.0, "qty": 0.001})
    await asyncio.sleep(0.05)
    assert any(e[0] == "buy_fill" for e in fired)
    await eng.stop()