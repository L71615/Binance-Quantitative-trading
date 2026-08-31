import pytest

from app.config import get_settings
from app.services.llm import LLMClient, LLMError, analyze_market


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_not_configured_returns_error(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    c = LLMClient()
    assert c.is_configured() is False
    import asyncio
    with pytest.raises(LLMError) as exc:
        asyncio.run(c.chat([{"role": "user", "content": "hi"}]))
    assert "not configured" in str(exc.value).lower()


def test_configured_check_blank(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    c = LLMClient()
    assert c.is_configured() is False


def test_configured_check_with_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    c = LLMClient()
    assert c.is_configured() is True
    assert c.base_url == "https://api.example.com/v1"
    assert c.api_key == "sk-test"


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    c = LLMClient()
    assert c.base_url == "https://api.example.com/v1"


def test_default_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    c = LLMClient()
    assert c.model == "deepseek-chat"


def test_analyze_market_not_configured(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    import asyncio
    with pytest.raises(LLMError):
        asyncio.run(analyze_market("BTCUSDT", "5m: +1%"))