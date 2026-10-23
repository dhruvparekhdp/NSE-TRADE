"""Postgres helpers for NSE — new database `nse_engine` on the same RDS as crypto."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS app_settings_history (
  id BIGSERIAL PRIMARY KEY,
  key TEXT NOT NULL,
  fingerprint TEXT,
  masked TEXT NOT NULL,
  saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  saved_by TEXT NOT NULL DEFAULT 'admin'
);
CREATE INDEX IF NOT EXISTS app_settings_history_key_idx ON app_settings_history(key, saved_at DESC);
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_ms BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  kind TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
"""


def database_url() -> str | None:
    raw = os.environ.get("DATABASE_URL", "").strip()
    return raw or None


def _psycopg_url(url: str) -> str:
    u = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    return u


def connect(url: str | None = None):
    import psycopg

    raw = _psycopg_url(url or database_url() or "")
    if not raw:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg.connect(raw)


def init_postgres(url: str | None = None) -> None:
    with connect(url) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def get_app_settings(url: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with connect(url) as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        for key, value in rows:
            try:
                out[key] = json.loads(value)
            except ValueError:
                continue
    return out


def save_app_setting(key: str, value: Any, url: str | None = None) -> None:
    payload = json.dumps(value)
    with connect(url) as conn:
        conn.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at
            """,
            (key, payload, datetime.now(UTC)),
        )
        conn.commit()


def clear_app_setting(key: str, url: str | None = None) -> None:
    """Crypto 'Clear' saves empty rather than DELETE — we store empty string sealed-or-not."""
    save_app_setting(key, "", url)


def append_settings_history(
    key: str,
    *,
    fingerprint: str | None,
    masked: str,
    saved_by: str = "admin",
    url: str | None = None,
) -> None:
    with connect(url) as conn:
        conn.execute(
            """
            INSERT INTO app_settings_history(key, fingerprint, masked, saved_by)
            VALUES (%s, %s, %s, %s)
            """,
            (key, fingerprint, masked, saved_by),
        )
        conn.commit()


def recent_settings_history(key: str, *, limit: int = 5, url: str | None = None) -> list[dict[str, Any]]:
    with connect(url) as conn:
        rows = conn.execute(
            """
            SELECT fingerprint, masked, saved_at, saved_by
            FROM app_settings_history
            WHERE key=%s
            ORDER BY saved_at DESC
            LIMIT %s
            """,
            (key, limit),
        ).fetchall()
    out = []
    for fp, masked, saved_at, saved_by in rows:
        out.append(
            {
                "fingerprint": fp,
                "masked": masked,
                "saved_ms": int(saved_at.timestamp() * 1000) if saved_at else None,
                "saved_by": saved_by,
            }
        )
    return out


def audit_event(kind: str, detail: str = "", url: str | None = None) -> None:
    try:
        with connect(url) as conn:
            conn.execute(
                "INSERT INTO audit_events(kind, detail) VALUES (%s, %s)",
                (kind, detail),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 — audit must never break the request
        pass


def nse_url_from_crypto_url(crypto_url: str, dbname: str = "nse_engine") -> str:
    """Rewrite path to nse_engine DB (used by deploy script on the server)."""
    raw = _psycopg_url(crypto_url)
    u = urlparse(raw)
    return urlunparse((u.scheme, u.netloc, f"/{dbname}", "", "", ""))


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
