# ruff: noqa
"""Replay Book A paper for 2026-10-30 using var/bt/replay_20261030 fixtures (C12 acceptance)."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import set_runtime_override  # noqa: E402
from engine.book_a_paper import JsonlMinuteBarSource, job_book_a_minute  # noqa: E402
from engine.state import init_db  # noqa: E402

FIX = ROOT / "var" / "bt" / "replay_20261030"
BARS = FIX / "bars_1m_20261030.jsonl"
SIGS = FIX / "signals_bookA_20261030.json"


def main() -> None:
    set_runtime_override("book_a_mode", "paper")
    conn = init_db(FIX / "replay_book_a.db")
    conn.execute("DELETE FROM signals")
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM book_a_signal_state")
    conn.execute("DELETE FROM paper_cycles WHERE book='A'")
    conn.commit()
    for row in json.loads(SIGS.read_text(encoding="utf-8")):
        conn.execute(
            "INSERT INTO signals(id, ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, features_json, decision, skip_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["id"],
                row["ts_ms"],
                row["trade_date"],
                row["symbol"],
                row["book"],
                row["strategy"],
                row["side"],
                row["role"],
                row["price"],
                row["stop"],
                row.get("target"),
                row.get("features_json"),
                row.get("decision"),
                row.get("skip_reason"),
            ),
        )
    conn.commit()
    src = JsonlMinuteBarSource(BARS)
    minutes: set[int] = set()
    with BARS.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ts = row["ts"]
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.hour < 9 or (dt.hour == 9 and dt.minute < 16) or dt.hour > 15:
                continue
            minutes.add(int(dt.timestamp() * 1000) // 60_000 * 60_000)
    totals: dict[str, int] = {"entries": 0, "exits": 0}
    refusals: Counter[str] = Counter()
    for ms in sorted(minutes):
        st = job_book_a_minute(conn, src, now_ms=ms + 59_000)
        totals["entries"] += int(st.get("entries") or 0)
        totals["exits"] += int(st.get("exits") or 0)
        for k, v in (st.get("refusals") or {}).items():
            refusals[k] += v
    # second full run
    for ms in sorted(minutes):
        job_book_a_minute(conn, src, now_ms=ms + 59_000)
    closed = conn.execute("SELECT exit_reason, net_inr, r_mult FROM trades WHERE book='A' AND status='closed'").fetchall()
    wallet = conn.execute("SELECT wallet FROM paper_cycles WHERE book='A' ORDER BY id DESC LIMIT 1").fetchone()
    open_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE book='A' AND status='open'").fetchone()["n"]
    print("entries", totals["entries"], "exits", totals["exits"])
    print("refusals", dict(refusals))
    print("exits_by_reason", dict(Counter(r["exit_reason"] for r in closed)))
    print("net_inr", sum(float(r["net_inr"] or 0) for r in closed))
    print("net_r", sum(float(r["r_mult"] or 0) for r in closed))
    print("final_wallet", wallet["wallet"] if wallet else None, "open", open_n)
    print("idempotent_ok", totals["entries"] == conn.execute("SELECT COUNT(*) FROM book_a_signal_state WHERE status='filled'").fetchone()[0])


if __name__ == "__main__":
    main()
