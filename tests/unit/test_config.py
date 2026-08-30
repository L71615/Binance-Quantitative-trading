import os

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults(monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    s = get_settings()
    assert s.binance_testnet is True
    assert s.binance_api_key == ""
    assert s.binance_api_secret == ""


def test_overrides(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET", "false")
    monkeypatch.setenv("BINANCE_API_KEY", "abc")
    monkeypatch.setenv("BINANCE_API_SECRET", "xyz")
    s = get_settings()
    assert s.binance_testnet is False
    assert s.binance_api_key == "abc"
    assert s.binance_api_secret == "xyz"
