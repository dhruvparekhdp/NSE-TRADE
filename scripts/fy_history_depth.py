"""Report daily/1m history depth for FY 2026-27 watchlist (V8-P1)."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from config.settings import get_settings
from data.lake import Lake
from news.watchlist import load_extra_name_hints

FY_START = date(2026, 4, 1)


def _scan_lake_daily(lake: Lake, symbols: list[str]) -> list[dict]:
    rows: list[dict] = []
    for sym in symbols:
        df = lake.read_daily(sym)
        if df is None or getattr(df, "empty", True):
            rows.append({"symbol": sym, "daily_rows": 0, "from": None, "to": None})
            continue
        dmin = int(df["date"].min())
        dmax = int(df["date"].max())
        fy = df[df["date"] >= int(FY_START.strftime("%Y%m%d"))]
        rows.append(
            {
                "symbol": sym,
                "daily_rows": int(len(df)),
                "from": dmin,
                "to": dmax,
                "fy_rows": int(len(fy)),
            }
        )
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--symbols", default=None, help="comma list; default watchlist extra keys")
    args = p.parse_args()
    s = get_settings()
    lake = Lake(args.lake or Path(s.data_dir) / "lake")
    if args.symbols:
        symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    else:
        symbols = sorted(load_extra_name_hints().keys())
    rows = _scan_lake_daily(lake, symbols)
    out = args.out or Path(s.data_dir) / "reports" / "fy_history_depth.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"fy_start": FY_START.isoformat(), "rows": rows}, indent=2), encoding="utf-8")
    md = out.with_suffix(".md")
    lines = [f"# FY history depth ({FY_START.isoformat()}+)\n", "| symbol | daily_rows | from | to | fy_rows |\n"]
    lines.append("|---|---:|---|---:|---:|\n")
    for r in rows:
        lines.append(
            f"| {r['symbol']} | {r['daily_rows']} | {r.get('from')} | {r.get('to')} | {r.get('fy_rows', 0)} |\n"
        )
    md.write_text("".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out), "md": str(md), "symbols": len(symbols)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
