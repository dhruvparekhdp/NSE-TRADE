"""Descriptive opening-gap study (V-NEXT N5). Not a PREREG trial."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.paths import lake_dir
from data.lake import Lake
from strategies.swing_breakout import bars_from_daily_df

IST = ZoneInfo("Asia/Kolkata")


def _fetch_spx_daily() -> dict[int, float]:
    """Prior US session close by IST date key YYYYMMDD (Yahoo ^GSPC)."""
    try:
        from urllib.request import Request, urlopen

        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=20y&interval=1d"
        req = Request(url, headers={"User-Agent": "nse-engine-research/0.1"})
        with urlopen(req, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode())
        ts = payload["chart"]["result"][0]["timestamp"]
        closes = payload["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        out: dict[int, float] = {}
        for t, c in zip(ts, closes, strict=False):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=IST).date()
            out[int(d.strftime("%Y%m%d"))] = float(c)
        return out
    except (OSError, KeyError, json.JSONDecodeError, IndexError):
        return {}


def gap_stats(bars) -> dict:
    if len(bars) < 2:
        return {}
    gaps = []
    for i in range(1, len(bars)):
        prev = bars[i - 1].close
        if prev <= 0:
            continue
        g = (bars[i].open - prev) / prev * 100.0
        oc = (bars[i].close - bars[i].open) / bars[i].open * 100.0 if bars[i].open else 0.0
        filled = (bars[i].low <= prev <= bars[i].high) if g > 0 else (bars[i].low <= prev <= bars[i].high)
        yr = datetime.fromtimestamp(bars[i].ts_ms / 1000, tz=IST).year
        gaps.append({"gap_pct": g, "open_to_close_pct": oc, "gap_filled": filled, "year": yr})
    return {"n": len(gaps), "gaps": gaps}


def bucket_report(gaps: list[dict]) -> dict:
    buckets = {"<-2": [], "-2..-0.5": [], "-0.5..0.5": [], "0.5..2": [], ">2": []}
    for g in gaps:
        x = g["gap_pct"]
        if x < -2:
            buckets["<-2"].append(g)
        elif x < -0.5:
            buckets["-2..-0.5"].append(g)
        elif x <= 0.5:
            buckets["-0.5..0.5"].append(g)
        elif x <= 2:
            buckets["0.5..2"].append(g)
        else:
            buckets[">2"].append(g)
    out = {}
    for k, rows in buckets.items():
        if not rows:
            continue
        out[k] = {
            "n": len(rows),
            "gap_fill_pct": sum(1 for r in rows if r["gap_filled"]) / len(rows) * 100.0,
            "avg_open_to_close": sum(r["open_to_close_pct"] for r in rows) / len(rows),
            "continuation_pct": sum(
                1
                for r in rows
                if (r["gap_pct"] > 0 and r["open_to_close_pct"] > 0)
                or (r["gap_pct"] < 0 and r["open_to_close_pct"] < 0)
            )
            / len(rows)
            * 100.0,
        }
    return out


def write_markdown(path: Path, body: dict) -> None:
    lines = [
        "# Opening gap study (descriptive, not a PREREG trial)",
        "",
        "Nifty 50 proxy and Nifty 100 names with gaps ≥ 2%. US prior session: S&P 500 (^GSPC) via Yahoo.",
        "",
        "## Nifty 50 proxy",
        "",
        f"- Sessions: **{body.get('nifty50', {}).get('n', 0)}**",
        f"- Gap vs prior US return correlation: **{body.get('us_corr', 'n/a')}**",
        "",
        "### By gap bucket",
        "",
        "| bucket | n | gap-fill % | avg open→close % | continuation % |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, v in (body.get("buckets") or {}).items():
        lines.append(
            f"| {k} | {v['n']} | {v['gap_fill_pct']:.1f} | {v['avg_open_to_close']:.2f} | {v['continuation_pct']:.1f} |"
        )
    lines.extend(["", "## Nifty 100 — gaps ≥ 2%", ""])
    big = body.get("large_gaps_n100") or {}
    lines.append(f"- Symbol-days with |gap| ≥ 2%: **{big.get('count', 0)}** (symbols scanned: {big.get('symbols', 0)})")
    lines.append("")
    lines.append("## By year (Nifty proxy)")
    for y, v in sorted((body.get("by_year") or {}).items()):
        lines.append(f"- **{y}**: n={v['n']} avg gap={v['avg_gap']:.2f}%")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default=None)
    p.add_argument("--out", default="docs/research/OPENING.md")
    p.add_argument("--json", default="var/reports/opening_study.json")
    args = p.parse_args(argv)
    lake = Lake(Path(args.lake or lake_dir()))
    nifty_sym = None
    for cand in ("NIFTYBEES", "RELIANCE", "SBIN"):
        if not lake.read_daily(cand).empty:
            nifty_sym = cand
            break
    body: dict = {}
    if nifty_sym:
        bars = bars_from_daily_df(lake.read_daily(nifty_sym).to_dict(orient="records"))
        gs = gap_stats(bars)
        gaps = gs.get("gaps") or []
        body["nifty50"] = {"n": gs.get("n", 0), "symbol_used": nifty_sym}
        body["buckets"] = bucket_report(gaps)
        by_year: dict[str, dict] = defaultdict(lambda: {"n": 0, "sum_gap": 0.0})
        for g in gaps:
            y = str(g["year"])
            by_year[y]["n"] += 1
            by_year[y]["sum_gap"] += g["gap_pct"]
        body["by_year"] = {y: {"n": v["n"], "avg_gap": v["sum_gap"] / v["n"]} for y, v in by_year.items() if v["n"]}
        spx = _fetch_spx_daily()
        pairs = []
        for g in gaps:
            d = datetime(g["year"], 1, 1, tzinfo=IST)  # placeholder — recompute from bar index
            _ = d
        # correlate using bar dates
        pairs = []
        for i in range(1, len(bars)):
            prev = bars[i - 1].close
            if prev <= 0:
                continue
            gap = (bars[i].open - prev) / prev
            day = int(datetime.fromtimestamp(bars[i].ts_ms / 1000, tz=IST).strftime("%Y%m%d"))
            # prior US: previous calendar day approximate
            us = spx.get(day - 1) or spx.get(day - 2)
            us_prev = spx.get(day - 2) or spx.get(day - 3)
            if us and us_prev and us_prev > 0:
                us_ret = (us - us_prev) / us_prev
                pairs.append((gap, us_ret))
        if len(pairs) > 10:
            mx = sum(p[0] for p in pairs) / len(pairs)
            my = sum(p[1] for p in pairs) / len(pairs)
            num = sum((p[0] - mx) * (p[1] - my) for p in pairs)
            den = (sum((p[0] - mx) ** 2 for p in pairs) * sum((p[1] - my) ** 2 for p in pairs)) ** 0.5
            body["us_corr"] = round(num / den, 3) if den else "n/a"
        else:
            body["us_corr"] = "insufficient US history"
    large = 0
    syms = sorted(p.stem for p in (lake.root / "bars_1d").glob("*.parquet")) if (lake.root / "bars_1d").exists() else []
    for sym in syms[:120]:
        df = lake.read_daily(sym)
        if df.empty or len(df) < 2:
            continue
        bars = bars_from_daily_df(df.to_dict(orient="records"))
        for i in range(1, len(bars)):
            prev = bars[i - 1].close
            if prev <= 0:
                continue
            if abs((bars[i].open - prev) / prev * 100.0) >= 2.0:
                large += 1
    body["large_gaps_n100"] = {"count": large, "symbols": len(syms)}
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(body, indent=2), encoding="utf-8")
    write_markdown(Path(args.out), body)
    print(json.dumps({"out": args.out, "json": args.json, "nifty50_n": body.get("nifty50", {}).get("n", 0)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
