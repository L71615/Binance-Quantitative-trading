"""Minimal OpenAI-compatible LLM client.

Works with any provider that exposes the `/chat/completions` endpoint with the
OpenAI schema (DeepSeek, OpenAI, Moonshot, etc.). No third-party SDK required.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class LLMError(Exception):
    """Raised when LLM is misconfigured or call fails."""

    def __init__(self, message: str, *, provider: str = "openai-compatible"):
        super().__init__(message)
        self.provider = provider


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        s = get_settings()
        self.base_url = (base_url or s.llm_base_url).rstrip("/")
        self.api_key = api_key or s.llm_api_key
        self.model = model or s.llm_model
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        if not self.is_configured():
            raise LLMError(
                "LLM not configured: set LLM_BASE_URL and LLM_API_KEY in .env"
            )
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise LLMError(f"transport error: {e}") from e
        if r.status_code >= 400:
            # Truncate response body to avoid logging secrets.
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"malformed response: {e}") from e


async def analyze_market(symbol: str, klines_summary: str) -> str:
    """Single-shot market analysis for a symbol. Returns LLM text."""
    c = LLMClient()
    sys_msg = (
        "You are a quantitative trading analyst. Be terse. "
        "Output: 1-line trend, 1-line risk note, 1-line suggested action. "
        "Use markdown. No preamble."
    )
    user_msg = f"Symbol: {symbol}\nRecent klines summary:\n{klines_summary}"
    return await c.chat(
        [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]
    )