"""Keys editable on /keys — stored encrypted in Postgres (DB wins over .env)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyField:
    key: str
    label: str
    help: str
    kind: str = "secret"  # secret | str


KEY_FIELDS: list[KeyField] = [
    KeyField("angel_api_key", "Angel SmartAPI key", "smartapi.angelone.in → Add App"),
    KeyField("angel_client_code", "Angel client code", "Login ID / client code"),
    KeyField("angel_pin", "Angel MPIN", "4-digit MPIN"),
    KeyField("angel_totp_secret", "Angel TOTP secret", "Enable TOTP on SmartAPI; base32 secret"),
    KeyField("groq_api_key", "Groq API key", "Same as crypto — console.groq.com"),
    KeyField("openrouter_api_key", "OpenRouter API key", "Same as crypto"),
    KeyField("hf_space_api_key", "HF Space API key", "Bearer for private Space"),
    KeyField("hf_base_url", "HF Space base URL", "e.g. https://….hf.space", kind="str"),
    KeyField("telegram_bot_token", "Telegram bot token", "Prefer a separate bot for NSE"),
    KeyField("telegram_chat_id", "Telegram chat id", "Your chat id", kind="str"),
    KeyField("session_secret", "Portal session secret", "Random string for cookie HMAC"),
    KeyField("expected_static_ip", "Expected static IP", "EC2 Elastic IP for live-order check", kind="str"),
]

BY_KEY = {f.key: f for f in KEY_FIELDS}
