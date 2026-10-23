"""Count every research trial (plan A11 / PLAN_V2 V2-6)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def connect(db_path: Path | str) -> sqlite3.Connection:
    from engine.state import init_db

    return init_db(db_path)


def data_hash_for(payload: str | bytes) -> str:
    raw = payload.encode() if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()[:16]


def record_trial(
    conn: sqlite3.Connection,
    *,
    strategy: str,
    params: dict[str, Any],
    data_from: str,
    data_to: str,
    period: str,
    n: int,
    avg_r: float,
    win_pct: float,
    passed: bool,
    report_path: str | None = None,
    post_hoc: bool = False,
    prereg_id: str | None = None,
    data_hash: str | None = None,
) -> int:
    params = dict(params)
    if post_hoc:
        params["post_hoc"] = True
    cur = conn.execute(
        """
        INSERT INTO lab_trials(
            ts_ms, strategy, params_json, data_from, data_to, period,
            n, avg_r, win_pct, passed, report_path, prereg_id, data_hash, post_hoc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(time.time() * 1000),
            strategy,
            json.dumps(params),
            data_from,
            data_to,
            period,
            n,
            avg_r,
            win_pct,
            1 if passed else 0,
            report_path,
            prereg_id,
            data_hash,
            1 if post_hoc else 0,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def trial_count(conn: sqlite3.Connection, strategy: str | None = None) -> int:
    if strategy:
        row = conn.execute("SELECT COUNT(*) AS c FROM lab_trials WHERE strategy=?", (strategy,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM lab_trials").fetchone()
    return int(row["c"])
