"""Load sealed secrets from Postgres into live Settings (DB wins)."""

from __future__ import annotations

import logging

from pydantic import SecretStr

from config.key_fields import BY_KEY, KEY_FIELDS
from config.secret_box import is_sealed, open_, seal
from config.settings import get_settings

log = logging.getLogger(__name__)


def apply_db_secrets() -> list[str]:
    """Read app_settings and setattr on cached Settings. Returns keys applied."""
    from storage.pg import database_url, get_app_settings, init_postgres

    if not database_url():
        log.info("no DATABASE_URL — keys stay from env/defaults")
        return []
    init_postgres()
    stored = get_app_settings()
    # Rebuild Settings only. reset_settings_cache() would also drop the SQLite runtime overrides that init_db
    # loaded before this runs (market_filter, kill_switch, max_open_swing: PLAN A6).
    get_settings.cache_clear()
    settings = get_settings()
    applied: list[str] = []
    for field in KEY_FIELDS:
        raw = stored.get(field.key)
        if raw is None or raw == "":
            continue
        value = open_(raw) if is_sealed(raw) else (raw if isinstance(raw, str) else None)
        if not value:
            continue
        if field.kind == "secret":
            setattr(settings, field.key, SecretStr(value))
        else:
            setattr(settings, field.key, value)
        applied.append(field.key)
    log.info("applied %s keys from database", len(applied))
    return applied


def save_key(key: str, value: str) -> None:
    from config.key_display import fingerprint, mask_value
    from storage.pg import append_settings_history, database_url, save_app_setting

    field = BY_KEY.get(key)
    if field is None:
        raise KeyError(key)
    value = value.strip()
    if not value:
        return
    stored = seal(value) if field.kind == "secret" else value
    save_app_setting(key, stored)
    # apply live
    settings = get_settings()
    if field.kind == "secret":
        setattr(settings, key, SecretStr(value))
    else:
        setattr(settings, key, value)
    if database_url():
        try:
            append_settings_history(
                key,
                fingerprint=fingerprint(value, key=key),
                masked=mask_value(value, kind=field.kind, key=key),
            )
        except Exception:  # noqa: BLE001
            log.warning("settings history append failed for %s", key)


def clear_key(key: str) -> None:
    from config.key_display import mask_value
    from storage.pg import append_settings_history, database_url, save_app_setting

    if key not in BY_KEY:
        raise KeyError(key)
    field = BY_KEY[key]
    save_app_setting(key, "")
    settings = get_settings()
    setattr(settings, key, None)
    if database_url():
        try:
            masked = mask_value("", kind=field.kind, key=key) or "(cleared)"
            append_settings_history(key, fingerprint=None, masked=masked)
        except Exception:  # noqa: BLE001
            log.warning("settings history clear-append failed for %s", key)
