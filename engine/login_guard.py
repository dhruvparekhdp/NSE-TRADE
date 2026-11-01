"""Stop repeated invalid MPIN logins (C9 scoped). Never stores MPIN or hashes."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS login_guard ("
        "day TEXT PRIMARY KEY, key_version_ms INTEGER NOT NULL DEFAULT 0, "
        "ab1007_streak INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0)"
    )


def secrets_key_version_ms() -> int:
    """Version = latest updated_at on Angel credential keys in Postgres (not a hash of the secret)."""
    try:
        from storage.pg import connect, database_url

        url = database_url()
        if not url:
            return 0
        with connect(url) as conn:
            row = conn.execute(
                "SELECT EXTRACT(EPOCH FROM MAX(updated_at)) * 1000 AS v FROM app_settings "
                "WHERE key IN ('angel_pin', 'angel_totp_secret', 'angel_api_key', 'angel_client_code')"
            ).fetchone()
            return int(row["v"] or 0) if row and row["v"] is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def _today_row(conn: sqlite3.Connection, version_ms: int) -> sqlite3.Row:
    _ensure(conn)
    day = datetime.now(tz=IST).date().isoformat()
    row = conn.execute("SELECT * FROM login_guard WHERE day=?", (day,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO login_guard(day, key_version_ms, ab1007_streak, blocked) VALUES (?,?,0,0)",
            (day, version_ms),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM login_guard WHERE day=?", (day,)).fetchone()
    elif int(row["key_version_ms"]) != version_ms:
        conn.execute(
            "UPDATE login_guard SET key_version_ms=?, ab1007_streak=0, blocked=0 WHERE day=?",
            (version_ms, day),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM login_guard WHERE day=?", (day,)).fetchone()
    assert row is not None
    return row


def login_blocked(conn: sqlite3.Connection) -> bool:
    version = secrets_key_version_ms()
    row = _today_row(conn, version)
    return bool(int(row["blocked"]))


def record_login_result(conn: sqlite3.Connection, *, ok: bool, error: str | None = None) -> None:
    version = secrets_key_version_ms()
    row = _today_row(conn, version)
    day = row["day"]
    if ok:
        conn.execute("UPDATE login_guard SET ab1007_streak=0, blocked=0 WHERE day=?", (day,))
        conn.commit()
        return
    err = (error or "").upper()
    if "AB1007" in err or "INVALID MPIN" in err:
        streak = int(row["ab1007_streak"]) + 1
        blocked = 1 if streak >= 2 else 0
        conn.execute(
            "UPDATE login_guard SET ab1007_streak=?, blocked=? WHERE day=?",
            (streak, blocked, day),
        )
        conn.commit()


def guard_status(conn: sqlite3.Connection) -> dict[str, int | bool]:
    version = secrets_key_version_ms()
    row = _today_row(conn, version)
    return {
        "blocked": bool(int(row["blocked"])),
        "ab1007_streak": int(row["ab1007_streak"]),
        "key_version_ms": int(row["key_version_ms"]),
    }
