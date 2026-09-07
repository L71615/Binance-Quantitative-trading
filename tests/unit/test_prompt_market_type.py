"""Tests for market-type-aware prompt templates."""
from app.services.ai_trader.prompt import (
    JSON_SCHEMA_TEXT,
    build_messages,
)


def _snapshot(**extra):
    base = {
        "symbol": "BTCUSDT",
        "price": 67000.0,
        "klines_summary": "(none)",
        "balances": [{"asset": "USDT", "free": "1000"}],
        "open_orders": [],
        "grid_has_open_orders": False,
    }
    base.update(extra)
    return base


def test_spot_prompt_says_spot_only():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="spot")
    sys_msg = msgs[0]["content"].lower()
    assert "spot" in sys_msg
    assert "leverage" not in sys_msg or "no leverage" in sys_msg


def test_futures_prompt_mentions_leverage():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    sys_msg = msgs[0]["content"]
    assert "leverage" in sys_msg.lower()
    assert "5" in sys_msg  # leverage value rendered


def test_futures_prompt_mentions_liquidation():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    sys_msg = msgs[0]["content"].lower()
    assert "liquidation" in sys_msg


def test_futures_user_message_includes_margin():
    msgs = build_messages(_snapshot(available_margin_usdt=1000.5),
                          symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    user_msg = msgs[1]["content"]
    assert "Available margin" in user_msg
    assert "1000.5" in user_msg


def test_futures_user_message_includes_mark_price():
    msgs = build_messages(_snapshot(mark_price=67238.2),
                          symbols_whitelist=["BTCUSDT"],
                          market_type="futures", leverage=5)
    user_msg = msgs[1]["content"]
    assert "Mark price" in user_msg
    assert "67238" in user_msg


def test_spot_user_message_does_not_include_margin():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                          market_type="spot")
    user_msg = msgs[1]["content"]
    assert "Available margin" not in user_msg


def test_default_market_type_is_spot():
    msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"])
    sys_msg = msgs[0]["content"].lower()
    assert "spot" in sys_msg


def test_schema_text_is_appended_to_both_templates():
    for mt in ("spot", "futures"):
        msgs = build_messages(_snapshot(), symbols_whitelist=["BTCUSDT"],
                              market_type=mt, leverage=5)
        assert JSON_SCHEMA_TEXT.split("{")[0] in msgs[0]["content"]
