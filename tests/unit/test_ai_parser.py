from app.services.ai_trader.parser import parse_response


WHITELIST = ["BTCUSDT", "ETHUSDT"]


def test_happy_path_action_hold():
    out = parse_response('{"action":"hold","symbol":"BTCUSDT","qty":0,"price":0,"reason":"no signal"}', WHITELIST)
    assert out == {
        "action": "hold", "symbol": "BTCUSDT", "qty": 0.0, "price": 0.0,
        "reason": "no signal",
    }


def test_strips_markdown_fences():
    raw = '```json\n{"action":"buy","symbol":"BTCUSDT","qty":0.01,"price":60000,"reason":"breakout above 60k"}\n```'
    out = parse_response(raw, WHITELIST)
    assert out["action"] == "buy"
    assert out["qty"] == 0.01
    assert out["price"] == 60000


def test_lowercase_symbol_uppercased():
    out = parse_response('{"action":"sell","symbol":"btcusdt","qty":0.01,"price":70000,"reason":"near upper bound"}', WHITELIST)
    assert out["symbol"] == "BTCUSDT"


def test_unknown_symbol_rejected():
    out = parse_response('{"action":"buy","symbol":"DOGEUSDT","qty":1,"price":0.1,"reason":"whatever"}', WHITELIST)
    assert out is None


def test_qty_zero_rejected_for_buy():
    out = parse_response('{"action":"buy","symbol":"BTCUSDT","qty":0,"price":60000,"reason":"no real buy"}', WHITELIST)
    assert out is None


def test_action_must_be_known():
    out = parse_response('{"action":"moon","symbol":"BTCUSDT","qty":0.01,"price":60000,"reason":"to the moon"}', WHITELIST)
    assert out is None


def test_reason_too_short_rejected():
    out = parse_response('{"action":"buy","symbol":"BTCUSDT","qty":0.01,"price":60000,"reason":"x"}', WHITELIST)
    assert out is None


def test_malformed_json_returns_none():
    assert parse_response("not json at all", WHITELIST) is None
    assert parse_response("{action:buy}", WHITELIST) is None
    assert parse_response("", WHITELIST) is None


def test_missing_field_rejected():
    raw = '{"action":"buy","symbol":"BTCUSDT","qty":0.01,"price":60000}'
    assert parse_response(raw, WHITELIST) is None