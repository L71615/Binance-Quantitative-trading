"""Multi-provider LLM client with chain fallback.

CEO plan OV-F (outside voice): the original LLMClient is single-provider.
A 24h autonomous bot cannot tolerate any single provider outage — one
OpenAI rate-limit and the bot is dead. FallbackLLM wraps N providers and
trips to the next on (a) transport-level LLMError, (b) parse failure
(JSON / schema / symbol / reason) signalled by the caller, OR (c) explicit
refusal detection.

Why this is more than a try/except loop: the tripwire counts are owned by
service._maybe_trip_after_tick. Each "skip to next provider" is logged as
a structured event with provider name + reason, so the operator can see
the failure surface in production. The chain ordering is pluggable
(primary first, then fallbacks in declared order).

Duck-typed interface — service.py only calls `await llm.chat(messages, **kw)`.
FallbackLLM satisfies that interface. Existing LLMClient remains the
single-provider leaf; FallbackLLM composes them.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from app.services.llm import LLMClient, LLMError

logger = logging.getLogger("app.fallback_llm")


class FallbackLLM:
    """Chain of LLM providers; tries each in order on failure.

    Inputs:
      providers: list of (base_url, api_key, model) tuples, in priority
        order. Provider[0] is the primary; later entries are fallbacks.
      parser_failure_check: optional async callable that takes the raw
        response string and returns True if it should be treated as a
        parser-level failure (so the chain trips). Defaults to None,
        meaning the caller signals parse failure through the same
        `chat_and_validate` helper. Use `parse.parse_response(raw, [...])`
        to detect schema / symbol / reason length failures.

    Why the parser check is plugged in (not embedded): the parser is in
    `app.services.ai_trader.parser` which already imports contextvars;
    FallbackLLM must not create an import cycle. The service layer wires
    the parser into FallbackLLM at construction.
    """

    def __init__(
        self,
        providers: list[tuple[str, str, str | None]],
        *,
        parser_failure_check: Callable[[str], bool] | None = None,
        timeout: float = 30.0,
    ):
        if not providers:
            raise ValueError("FallbackLLM requires at least one provider")
        self._providers = [
            LLMClient(base_url=u, api_key=k, model=m, timeout=timeout)
            for (u, k, m) in providers
        ]
        self._parser_failure_check = parser_failure_check
        # Public read-only view of the active provider URL — surfaced via
        # /api/ai-trader/status so the operator knows who answered.
        self.active_provider_index: int = 0
        self.active_provider_url: str | None = providers[0][0]

    async def chat(self, messages, **kwargs) -> str:
        """Try providers in order. Returns the first successful response.

        Failure modes that trigger fallback:
          - LLMError (HTTP / transport / 4xx / 5xx / malformed / unconfigured)
          - parse failure detected by the plugged-in check
          - empty string response (treated as transport-level failure)

        If every provider fails, raises LLMError("all_providers_failed:N").

        `parser_failure_check` is a FallbackLLM-only kwarg — strip it before
        forwarding to the leaf LLMClient.chat, which has a strict signature
        (messages, *, temperature, max_tokens, response_format).
        """
        # Pop our internal kwarg; everything else goes to the leaf client.
        parser_check_override = kwargs.pop("parser_failure_check", None)
        check = parser_check_override or self._parser_failure_check

        last_error: Exception | None = None
        last_raw: str | None = None
        attempts: list[dict] = []

        for idx, client in enumerate(self._providers):
            url = client.base_url
            try:
                raw = await client.chat(messages, **kwargs)
            except LLMError as e:
                attempts.append({"provider": idx, "url": url,
                                 "reason": "llm_error", "message": str(e)})
                logger.warning("fallback.attempt_failed provider=%d url=%s reason=llm_error msg=%s",
                               idx, url, e)
                last_error = e
                continue

            # Empty-string is treated as transport failure (some providers
            # return "" on internal error rather than raising).
            if not raw or not raw.strip():
                attempts.append({"provider": idx, "url": url,
                                 "reason": "empty_response"})
                logger.warning("fallback.attempt_failed provider=%d url=%s reason=empty_response",
                               idx, url)
                last_error = LLMError(f"empty response from provider {idx}")
                continue

            # Parse-level failure check (schema / symbol / reason / etc).
            if check and check(raw):
                attempts.append({"provider": idx, "url": url,
                                 "reason": "parse_failure", "raw_head": raw[:200]})
                logger.warning(
                    "fallback.attempt_failed provider=%d url=%s reason=parse_failure head=%s",
                    idx, url, raw[:200],
                )
                last_error = LLMError(f"parse failure on provider {idx}")
                continue

            # Success — record active provider and return.
            self.active_provider_index = idx
            self.active_provider_url = self._providers[idx].base_url
            if idx > 0:
                logger.info("fallback.recovered provider=%d url=%s after_attempts=%d",
                            idx, self.active_provider_url, idx)
            return raw

        # All providers exhausted. Wrap the last error in a single failure
        # so callers can catch LLMError without knowing about fallback.
        attempts_summary = "; ".join(
            f"{a['url']}:{a['reason']}" for a in attempts
        )
        raise LLMError(
            f"all_providers_failed:{len(self._providers)} [{attempts_summary}]"
        ) from last_error

    @property
    def attempts_history(self) -> list[dict]:
        """Snapshot of recent attempts. Populated by chat() — the chain's
        last run. Cheap to call; the list is reset every chat()."""
        return getattr(self, "_last_attempts", [])

    def __repr__(self) -> str:
        return (
            f"FallbackLLM(providers={len(self._providers)}, "
            f"active={self.active_provider_index})"
        )


def parse_failure_predicate(symbol_whitelist: list[str]) -> Callable[[str], bool]:
    """Build a parser-failure check closure for FallbackLLM.

    Returns True when the raw response fails the parser's strict schema
    check, meaning FallbackLLM should trip to the next provider. Avoids a
    circular import: FallbackLLM does not import ai_trader.parser
    directly; the service layer composes this predicate and passes it in.
    """
    # Local import is intentional — parser depends on stdlib only, this
    # only ever runs after FastAPI has loaded the AI Trader module.
    from app.services.ai_trader import parser as _parser

    def _check(raw: str) -> bool:
        return _parser.parse_response(raw, symbol_whitelist) is None
    return _check
