"""SQLite state store + migrations (plan A7.1 / P0-4)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from config.settings import set_runtime_override

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    ver = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    return int(ver["v"]) if ver else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply numbered *.sql migrations. Second call is a no-op. Returns version."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    version = _current_version(conn)
    for path in files:
        # e.g. 001_init.sql -> 1
        num = int(path.name.split("_", 1)[0])
        if num <= version:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version(version, applied_ms) VALUES (?, ?)",
            (num, int(time.time() * 1000)),
        )
        conn.commit()
        version = num
    return version


def init_db(db_path: Path | str) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    _load_runtime_overrides(conn)
    return conn


def _load_runtime_overrides(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
    for row in rows:
        set_runtime_override(row["key"], json.loads(row["value_json"]))


def set_setting(conn: sqlite3.Connection, key: str, value: Any, updated_by: str = "system") -> None:
    payload = json.dumps(value)
    now = int(time.time() * 1000)
    conn.execute(
        """
        INSERT INTO settings(key, value_json, updated_ms, updated_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value_json=excluded.value_json,
          updated_ms=excluded.updated_ms,
          updated_by=excluded.updated_by
        """,
        (key, payload, now, updated_by),
    )
    conn.commit()
    set_runtime_override(key, value)


def append_event(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> int:
    cur = conn.execute(
        "INSERT INTO events(ts_ms, kind, json) VALUES (?, ?, ?)",
        (int(time.time() * 1000), kind, json.dumps(payload)),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_instrument(conn: sqlite3.Connection, **fields: Any) -> None:
    cols = [
        "symbol",
        "token",
        "trading_symbol",
        "name",
        "isin",
        "tick_size",
        "lot_size",
        "in_universe",
        "updated_ms",
    ]
    values = [fields.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "symbol")
    conn.execute(
        f"INSERT INTO instruments({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(symbol) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()


def get_instrument(conn: sqlite3.Connection, symbol: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM instruments WHERE symbol=?", (symbol,)).fetchone()
    return dict(row) if row else None
