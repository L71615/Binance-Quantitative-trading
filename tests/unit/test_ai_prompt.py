from app.services.ai_trader.prompt import build_messages, JSON_SCHEMA_TEXT

SNAPSHOT = {
    "symbol": "BTCUSDT",
    "price": 60380.0,
    "klines_summary": "O60000 H60100 L59900 C60050 V10 | ...",
    "balances": [{"asset": "BTC", "free": "0.005", "locked": "0.001"}],
    "open_orders": [],
    "grid_has_open_orders": False,
}


def test_json_schema_lists_whitelisted_symbols():
    text = JSON_SCHEMA_TEXT.format(symbols="BTCUSDT")
    assert '"BTCUSDT"' in text
    assert "buy|sell|hold" in text


def test_build_messages_returns_two_messages():
    out = build_messages(SNAPSHOT, symbols_whitelist=["BTCUSDT"])
    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "user"


def test_build_messages_embeds_snapshot_in_user():
    out = build_messages(SNAPSHOT, symbols_whitelist=["BTCUSDT"])
    body = out[1]["content"]
    assert "60380" in body
    assert "BTC" in body  # balance line visible


def test_build_messages_system_mentions_risk():
    out = build_messages(SNAPSHOT, symbols_whitelist=["BTCUSDT"])
    sys = out[0]["content"]
    assert "spot" in sys.lower() or "Spot" in sys
    assert "whitelist" in sys.lower() or "whitelisted" in sys.lower()
