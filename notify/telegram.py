"""Telegram sender + command router (plan A13.3 / P0-6). No-op when unconfigured."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from config.settings import get_settings

log = logging.getLogger(__name__)

CommandHandler = Callable[[str, list[str]], Awaitable[str | None] | str | None]


class TelegramClient:
    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self.token = token
        if self.token is None and settings.telegram_bot_token:
            self.token = settings.telegram_bot_token.get_secret_value()
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id
        self._http = http
        self._owns_http = http is None
        self.base_url = base_url or "https://api.telegram.org"
        self._commands: dict[str, CommandHandler] = {}

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def on_command(self, name: str, handler: CommandHandler) -> None:
        self._commands[name.lstrip("/").lower()] = handler

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=20.0)
        return self._http

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()

    async def send(self, text: str, *, chat_id: str | None = None) -> bool:
        """Send a message. Returns False (no-op) when unconfigured. Never logs secrets."""
        if not self.configured:
            log.debug("telegram unconfigured; drop message")
            return False
        cid = chat_id or self.chat_id
        assert self.token and cid
        client = await self._client()
        url = f"/bot{self.token}/sendMessage"
        resp = await client.post(url, json={"chat_id": cid, "text": text})
        resp.raise_for_status()
        return True

    async def handle_update(self, update: dict[str, Any]) -> str | None:
        """Route an inbound update. Only accepts messages from settings.telegram_chat_id."""
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not self.chat_id or chat_id != str(self.chat_id):
            log.warning("ignored telegram chat_id mismatch")
            return None
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return None
        parts = text.split()
        cmd = parts[0].lstrip("/").split("@", 1)[0].lower()
        args = parts[1:]
        handler = self._commands.get(cmd)
        if handler is None:
            return f"unknown command /{cmd}"
        result = handler(cmd, args)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        return result
