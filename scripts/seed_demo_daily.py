"""Seed synthetic daily bars so research/backtest works before Angel keys.

  python -m scripts.seed_demo_daily --symbols SBIN,RELIANCE --years 8
"""

from __future__ import annotations

import argparse
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data.calendar import load_default_calendar
from data.lake import Lake


def synth(symbol: str, start: date, end: date, seed: float = 100.0) -> pd.DataFrame:
    cal = load_default_calendar()
    rows = []
    px = seed
    i = 0
    cur = start
    while cur <= end:
        if cal.is_trading_day(cur) or (cur.year < 2026 and cur.weekday() < 5):
            # quiet grind, then a clear breakout every ~45 sessions (for S6 lab demos)
            o = px
            if i > 60 and i % 45 == 0:
                c = px * 1.04
                h = c * 1.005
                lo = o * 0.995
            else:
                drift = 1.0 + 0.0003 + 0.0008 * math.sin(i / 18.0)
                c = px * drift
                h = max(o, c) * 1.004
                lo = min(o, c) * 0.996
            rows.append(
                {
                    "date": int(cur.strftime("%Y%m%d")),
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(lo, 2),
                    "close": round(c, 2),
                    "volume": 1_000_000 + (i % 50) * 10_000,
                    "delivery_qty": 400_000,
                    "source": "synth",
                    "adj_close": round(c, 2),
                }
            )
            px = c
            i += 1
        cur += timedelta(days=1)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default="./data/lake")
    p.add_argument("--symbols", default="SBIN,RELIANCE,TCS,INFY,HDFCBANK")
    p.add_argument("--years", type=int, default=8)
    args = p.parse_args(argv)
    lake = Lake(Path(args.lake))
    end = date.today()
    start = date(end.year - args.years, end.month, end.day)
    for i, sym in enumerate(args.symbols.split(",")):
        sym = sym.strip().upper()
        df = synth(sym, start, end, seed=100 + i * 40)
        n = lake.write_daily(sym, df)
        print(sym, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
