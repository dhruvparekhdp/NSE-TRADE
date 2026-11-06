"""The only reader of Angel SmartAPI credentials (plan A6 / NSE-003).

The key, client code, MPIN and TOTP seed live in the environment or in the
encrypted secret store. ``config.secrets_loader`` copies the store into
Settings. This module is what broker code calls. It raises before any broker
call when one of the four is missing, and the error names the fields only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Env name, then the Settings attribute. Order is the order of a missing-field error.
BROKER_SECRET_FIELDS: tuple[tuple[str, str], ...] = (
    ("ANGEL_API_KEY", "angel_api_key"),
    ("ANGEL_CLIENT_CODE", "angel_client_code"),
    ("ANGEL_PIN", "angel_pin"),
    ("ANGEL_TOTP_SECRET", "angel_totp_secret"),
)


class BrokerSecretsMissing(RuntimeError):
    """One or more Angel credentials are unset. ``missing`` is env names, never values."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        names = ", ".join(self.missing)
        super().__init__(
            f"Angel credentials missing: {names}. "
            "Set them in the environment or the secret store. No broker call was made."
        )


@dataclass(frozen=True)
class BrokerSecrets:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return str(value.get_secret_value()).strip()
    return str(value).strip()


def load_broker_secrets() -> BrokerSecrets:
    """Return the four Angel credentials or raise BrokerSecretsMissing."""
    from config.settings import get_settings

    settings = get_settings()
    found: dict[str, str] = {}
    missing: list[str] = []
    for env_name, attr in BROKER_SECRET_FIELDS:
        text = _plain(getattr(settings, attr, None))
        if not text:
            missing.append(env_name)
        else:
            found[env_name] = text
    if missing:
        raise BrokerSecretsMissing(missing)
    return BrokerSecrets(
        api_key=found["ANGEL_API_KEY"],
        client_code=found["ANGEL_CLIENT_CODE"],
        pin=found["ANGEL_PIN"],
        totp_secret=found["ANGEL_TOTP_SECRET"],
    )
