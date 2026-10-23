"""Backfill helpers.

  # From a local bhavcopy CSV/zip (no Angel key needed):
  python -m scripts.backfill --bhav path/to/bhav.csv

  # Angel 1m (needs keys in .env) — evening:
  python -m scripts.backfill --angel --symbol SBIN --token 3045 --days 30
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from config.paths import lake_dir
from data.history import ingest_bhav_to_lake, parse_bhavcopy_csv, parse_bhavcopy_zip, window_30d
from data.lake import Lake


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default=None, help="default: settings.data_dir/lake")
    p.add_argument("--bhav", help="CSV or ZIP bhavcopy path")
    p.add_argument("--angel", action="store_true")
    p.add_argument("--symbol")
    p.add_argument("--token")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args(argv)
    lake = Lake(Path(args.lake) if args.lake else lake_dir())

    if args.bhav:
        path = Path(args.bhav)
        raw = path.read_bytes()
        if path.suffix.lower() == ".zip":
            df = parse_bhavcopy_zip(raw)
        else:
            df = parse_bhavcopy_csv(raw.decode("utf-8", errors="replace"))
        counts = ingest_bhav_to_lake(lake, df)
        print({"ingested": counts, "symbols": len(counts)})
        return 0

    if args.angel:
        print("Angel backfill: wire SmartConnect in evening via scripts/login_check then history.")
        print("Windows:", len(window_30d(date.today() - timedelta(days=args.days), date.today())))
        return 0

    p.error("provide --bhav or --angel")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
