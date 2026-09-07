def test_crypto_store_service_name_is_renamed():
    from app.crypto_store import SERVICE_NAME
    assert SERVICE_NAME == "binance-trading-bot"


def test_crypto_store_service_name_no_longer_spot_only():
    from app.crypto_store import SERVICE_NAME
    assert "spot" not in SERVICE_NAME.lower()
