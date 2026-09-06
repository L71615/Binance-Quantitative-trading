"""P0-4: FallbackLLM chains providers and trips on parse/transport failures.

CEO plan OV-F: a single-provider LLMClient cannot survive 24h. FallbackLLM
must skip to the next provider when the current one returns (a) an LLMError
(HTTP / transport / 4xx / 5xx / malformed / unconfigured), (b) an empty
response, or (c) a parse failure per the plugged-in check. These tests pin
each branch without making real network calls — the LLMClient instances
inside FallbackLLM are replaced with async stubs.
"""
import asyncio

import pytest

from app.services.fallback_llm import FallbackLLM
from app.services.llm import LLMError


class _StubClient:
    """Async LLMClient stand-in. Configure behavior per provider."""

    def __init__(self, *, raises: Exception | None = None,
                 returns: str | None = None, base_url: str = "stub"):
        self.raises = raises
        self.returns = returns
        self.base_url = base_url
        self.calls = 0

    async def chat(self, messages, **kwargs) -> str:
        self.calls += 1
        if self.raises:
            raise self.raises
        if self.returns is not None:
            return self.returns
        return "default"


def _build(*clients) -> FallbackLLM:
    """Wire a chain of stub clients into a FallbackLLM. The chain's
    internal LLMClients are replaced with the stubs so no network call
    happens."""
    fb = FallbackLLM([(c.base_url, "key", "model") for c in clients])
    fb._providers = list(clients)
    return fb


# ----- Construction -----------------------------------------------------------


def test_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        FallbackLLM([])


def test_primary_is_active_at_construction():
    fb = _build(_StubClient(base_url="primary"))
    assert fb.active_provider_index == 0
    assert fb.active_provider_url == "primary"


# ----- Happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_primary_response_when_it_succeeds():
    fb = _build(_StubClient(returns="from-primary", base_url="primary"),
                _StubClient(returns="from-fallback", base_url="fb"))
    out = await fb.chat([{"role": "user", "content": "x"}])
    assert out == "from-primary"
    assert fb.active_provider_index == 0
    assert fb._providers[0].calls == 1
    assert fb._providers[1].calls == 0  # fallback never reached


# ----- Failure triggers -------------------------------------------------------


@pytest.mark.asyncio
async def test_trips_on_llm_error():
    fb = _build(
        _StubClient(raises=LLMError("HTTP 429"), base_url="primary"),
        _StubClient(returns="ok", base_url="fb"),
    )
    out = await fb.chat([{"role": "user", "content": "x"}])
    assert out == "ok"
    assert fb.active_provider_index == 1


@pytest.mark.asyncio
async def test_trips_on_empty_response():
    fb = _build(
        _StubClient(returns="", base_url="primary"),
        _StubClient(returns="ok", base_url="fb"),
    )
    out = await fb.chat([{"role": "user", "content": "x"}])
    assert out == "ok"
    assert fb.active_provider_index == 1


@pytest.mark.asyncio
async def test_trips_on_parse_failure():
    """Parse failure on provider 0 → falls through to provider 1.

    The parser check returns True only for primary's response; secondary's
    response is valid so it returns the recovery."""
    fb = _build(
        _StubClient(returns="<not-json>", base_url="primary"),
        _StubClient(returns="ok", base_url="fb"),
    )
    out = await fb.chat([{"role": "user", "content": "x"}],
                        parser_failure_check=lambda r: r == "<not-json>")
    assert out == "ok"
    assert fb.active_provider_index == 1


@pytest.mark.asyncio
async def test_no_fallback_when_parser_says_ok():
    """If the parser check returns False (response is valid), we do NOT
    skip to the next provider — we keep the response."""
    fb = _build(
        _StubClient(returns='{"action":"hold"}', base_url="primary"),
        _StubClient(returns="from-fb", base_url="fb"),
    )
    out = await fb.chat([{"role": "user", "content": "x"}],
                        parser_failure_check=lambda r: False)
    assert out == '{"action":"hold"}'
    assert fb.active_provider_index == 0


@pytest.mark.asyncio
async def test_does_not_trip_on_strip_whitespace_only():
    """A response of '   \\n  ' (whitespace only) is treated as empty and
    triggers fallback. This catches a class of providers that return
    whitespace on internal errors."""
    fb = _build(
        _StubClient(returns="   \n  ", base_url="primary"),
        _StubClient(returns="ok", base_url="fb"),
    )
    out = await fb.chat([{"role": "user", "content": "x"}])
    assert out == "ok"
    assert fb.active_provider_index == 1


# ----- All-providers-exhausted ------------------------------------------------


@pytest.mark.asyncio
async def test_raises_when_every_provider_fails():
    fb = _build(
        _StubClient(raises=LLMError("HTTP 500"), base_url="p1"),
        _StubClient(raises=LLMError("timeout"), base_url="p2"),
        _StubClient(returns="<bad>", base_url="p3"),
    )
    fb._parser_failure_check = lambda r: True  # p3 also fails
    with pytest.raises(LLMError) as exc_info:
        await fb.chat([{"role": "user", "content": "x"}])
    msg = str(exc_info.value)
    assert "all_providers_failed:3" in msg
    assert "p1:llm_error" in msg
    assert "p2:llm_error" in msg
    assert "p3:parse_failure" in msg
    # Original last exception is chained via `from`.
    assert exc_info.value.__cause__ is not None


# ----- Active-provider observability ------------------------------------------


@pytest.mark.asyncio
async def test_recovery_logs_active_provider_switch():
    """When fallback recovers, active_provider_index updates so /status
    can surface which provider currently answers."""
    fb = _build(
        _StubClient(raises=LLMError("boom"), base_url="primary"),
        _StubClient(returns="recovered", base_url="secondary"),
    )
    await fb.chat([{"role": "user", "content": "x"}])
    assert fb.active_provider_index == 1
    assert fb.active_provider_url == "secondary"
    # Next call uses the recovered provider as the active one — unless it
    # also fails, then we keep walking.
    await fb.chat([{"role": "user", "content": "x"}])
    assert fb.active_provider_index == 1
    assert fb._providers[1].calls == 2
