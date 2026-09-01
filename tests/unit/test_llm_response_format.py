import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.llm import LLMClient


@pytest.mark.asyncio
async def test_chat_forwards_response_format(monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None, headers=None, **kw):
        captured["url"] = url
        captured["json"] = json
        req = httpx.Request("POST", url, json=json, headers=headers)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"action":"hold"}'}}]},
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    c = LLMClient(base_url="https://x.example", api_key="k", model="m")
    out = await c.chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    assert out == '{"action":"hold"}'
    assert captured["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_chat_omits_response_format_when_none(monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None, headers=None, **kw):
        captured["json"] = json
        req = httpx.Request("POST", url, json=json, headers=headers)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}, request=req
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    c = LLMClient(base_url="https://x.example", api_key="k", model="m")
    await c.chat([{"role": "user", "content": "hi"}])
    assert "response_format" not in captured["json"]