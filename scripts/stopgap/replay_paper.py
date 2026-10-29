# ruff: noqa
# Reference copy (Claude, 30 Oct 2026): replays the paper jobs on a copy of engine.db; see C17.
"""End-to-end paper test on a COPY of the server's engine.db + daily lake (var/bt/replay/), 26-29 Oct 2026.
Runs the engine's own jobs in production order each day: job_eod_fill (16:15) then job_scan (16:20).
FILTER=off replaces F1/F2 with "no skip" to show whether the paper path itself works; FILTER=on is production.
Run from repo root:  FILTER=off python var/bt/replay_paper.py"""
import os
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import engine.paper_jobs as pj  # noqa: E402
from data.lake import Lake  # noqa: E402

R = Path(__file__).resolve().parents[2] / "var" / "bt" / "replay"
src = R / "engine_snapshot.db"
db = R / f"replay_{os.environ.get('FILTER', 'off')}.db"
db.write_bytes(src.read_bytes())
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
lake = Lake(R / "lake")
if os.environ.get("FILTER", "off") == "off":
    pj.f1_skip_reason = lambda *a, **k: None
    pj.f2_skip_reason = lambda *a, **k: None
ENABLED = ["S6_swing", "S6b_keltner"]
for d in (date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)):
    fills = pj.job_eod_fill(conn, lake, trade_date=d)
    rows = pj.job_scan(conn, lake, trade_date=d, enabled=ENABLED, write=True)
    picks = [r for r in rows if r["role"] == "pick"]
    print(
        f"{d}  fills={len(fills) if fills is not None else 0}  picks={len(picks)}  "
        f"decisions={dict(Counter(r['decision'] for r in picks))}  "
        f"skips={dict(Counter(r['skip_reason'] for r in picks if r['skip_reason']))}"
    )
    for f in fills or []:
        print(
            "     fill:",
            {k: f.get(k) for k in ("symbol", "strategy", "action", "qty", "price", "reason", "status") if k in f}
            or f,
        )
print("\npending :", [tuple(r) for r in conn.execute("select trade_date, symbol, strategy, qty, limit_price from pending_orders")])
print("holdings:", [tuple(r) for r in conn.execute("select * from holdings")][:10])
print("trades  :", conn.execute("select count(*) from trades").fetchone()[0])
print("wallet  :", [tuple(r) for r in conn.execute("select id, wallet, peak_wallet, status from paper_cycles")])
