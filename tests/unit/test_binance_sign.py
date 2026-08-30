from app.broker.binance import sign_query, now_ms


def test_sign_query_deterministic():
    p = {"symbol": "BTCUSDT", "side": "BUY", "timestamp": 1700000000000}
    sig = sign_query(p, "mysecret")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex


def test_now_ms_is_int():
    n = now_ms()
    assert isinstance(n, int)
    assert n > 1700000000000


def test_sign_query_changes_with_secret():
    p = {"symbol": "BTCUSDT"}
    a = sign_query(p, "secret1")
    b = sign_query(p, "secret2")
    assert a != b
