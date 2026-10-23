"""P0-6: telegram no-op when unconfigured; chat-id check; fake API send."""

from __future__ import annotations

import httpx
import pytest

from notify.telegram import TelegramClient


@pytest.mark.asyncio
async def test_send_noop_when_unconfigured():
    client = TelegramClient(token=None, chat_id=None)
    assert client.configured is False
    assert await client.send("hello") is False


@pytest.mark.asyncio
async def test_send_hits_fake_api():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://api.telegram.org")
    client = TelegramClient(token="tok", chat_id="42", http=http)
    assert await client.send("hi there") is True
    assert len(calls) == 1
    assert "/bottok/sendMessage" in str(calls[0].url)
    await http.aclose()


@pytest.mark.asyncio
async def test_command_router_rejects_other_chat():
    client = TelegramClient(token="tok", chat_id="42")

    async def status(_cmd: str, _args: list[str]) -> str:
        return "ok"

    client.on_command("status", status)
    out = await client.handle_update(
        {"message": {"chat": {"id": 99}, "text": "/status"}}
    )
    assert out is None


@pytest.mark.asyncio
async def test_command_router_accepts_owner_chat():
    client = TelegramClient(token="tok", chat_id="42")

    async def status(_cmd: str, _args: list[str]) -> str:
        return "all good"

    client.on_command("status", status)
    out = await client.handle_update(
        {"message": {"chat": {"id": 42}, "text": "/status"}}
    )
    assert out == "all good"
