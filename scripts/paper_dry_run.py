"""Dry-run job_scan for one date (V-FIX-2 F1d)."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from config.paths import lake_dir
from data.lake import Lake
from engine.paper_jobs import job_scan
from engine.state import init_db


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD scan date (closed daily bar)")
    p.add_argument("--lake", default=None)
    p.add_argument("--db", default=None)
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--symbols", default="")
    args = p.parse_args(argv)
    td = date.fromisoformat(args.date)
    lake = Lake(Path(args.lake or lake_dir()))
    db_path = Path(args.db) if args.db else Path(lake_dir()).parent / "engine.db"
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    if args.no_write:
        conn = init_db(":memory:")
    else:
        conn = init_db(db_path)
    rows = job_scan(
        conn,
        lake,
        trade_date=td,
        enabled=[],
        symbols=syms,
        write=not args.no_write and conn is not None,
    )
    for r in rows:
        print(
            f"{r['trade_date']} {r['symbol']} {r['strategy']} role={r['role']} "
            f"decision={r['decision']} skip={r.get('skip_reason')}"
        )
    print({"signals": len(rows), "write": not args.no_write})
    if conn is not None:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
