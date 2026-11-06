"""Strip Angel credentials from log lines (plan A14.3 / NSE-003).

The API key and TOTP seed are removed wherever they appear. The MPIN and
client code are removed when a log names that field (``pin=…``). A 4-digit
MPIN is not stripped out of unrelated numbers such as prices.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[REDACTED]"

# Longer names first so ``totp_secret`` is not partially matched as ``secret``.
_ASSIGN = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(angel_totp_secret|totp_secret|totp_seed|angel_api_key|api_key|apikey|"
    r"angel_client_code|client_code|clientcode|angel_pin|refresh_token|feed_token|"
    r"mpin|password|secret|token|jwt|totp|pin)"
    r"(\s*[=:]\s*)(\S+)"
)

_installed = False
_orig_format = logging.Formatter.format


def _configured_secrets() -> list[str]:
    """Long credential values currently loaded. Short pins are handled by field names."""
    try:
        from config.settings import get_settings

        settings = get_settings()
    except Exception:  # noqa: BLE001 — logging must not break if settings fail
        return []
    found: list[str] = []
    for _env_name, attr in (
        ("ANGEL_API_KEY", "angel_api_key"),
        ("ANGEL_CLIENT_CODE", "angel_client_code"),
        ("ANGEL_PIN", "angel_pin"),
        ("ANGEL_TOTP_SECRET", "angel_totp_secret"),
    ):
        raw = getattr(settings, attr, None)
        if raw is None:
            continue
        text = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
        text = str(text).strip()
        if len(text) >= 8:
            found.append(text)
    found.sort(key=len, reverse=True)
    return found


def redact_message(text: str, secrets: list[str] | None = None) -> str:
    """Return ``text`` with credential values replaced by ``[REDACTED]``."""
    values = _configured_secrets() if secrets is None else list(secrets)
    values.sort(key=len, reverse=True)
    out = text
    for value in values:
        if len(value) >= 8 and value in out:
            out = out.replace(value, REDACTED)
    return _ASSIGN.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", out)


def install_log_redaction() -> None:
    """Patch the stdlib formatter once. Later handlers pick this up."""
    global _installed
    if _installed:
        return

    def _format(self: logging.Formatter, record: logging.LogRecord) -> str:
        return redact_message(_orig_format(self, record))

    logging.Formatter.format = _format  # type: ignore[method-assign]
    _installed = True

