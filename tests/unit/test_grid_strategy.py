import pytest

from app.strategy.grid import build_grid_levels, GridStrategy


def test_arithmetic_grid_levels_count_and_bounds():
    levels = build_grid_levels(100.0, 200.0, 11, "arithmetic")
    assert len(levels) == 11
    assert levels[0] == pytest.approx(100.0)
    assert levels[-1] == pytest.approx(200.0)
    diffs = [levels[i+1] - levels[i] for i in range(len(levels) - 1)]
    assert max(diffs) - min(diffs) < 1e-6


def test_geometric_grid_levels_count_and_bounds():
    levels = build_grid_levels(100.0, 200.0, 5, "geometric")
    assert len(levels) == 5
    assert levels[0] == pytest.approx(100.0)
    assert levels[-1] == pytest.approx(200.0)


def test_grid_strategy_starts_with_two_sided_orders(monkeypatch):
    placed = []

    def fake_place_order(**kw):
        placed.append(kw)
        return {"orderId": len(placed)}

    from app.strategy.base import StrategyContext
    s = GridStrategy("BTCUSDT", 100.0, 110.0, count=6, mode="arithmetic", total_quote_amount=60.0)
    ctx = StrategyContext(place_order=fake_place_order, log=lambda m: None)
    s.on_start(ctx)
    # Roughly: levels between 100 and 110, around current price = midpoint 105
    # Two-sided means at least one BUY below midpoint and one SELL above.
    sides = [p["side"] for p in placed]
    assert "BUY" in sides
    assert "SELL" in sides
    assert len(placed) >= 2