"""Build the daily lake from bhav copies + corporate actions (PLAN_V2 V3-1 / V1-7)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from data.corporate_actions import CorpAction, adj_factor_on
from data.history import parse_bhavcopy_csv
from data.lake import Lake


def load_corp_actions(path: Path) -> list[CorpAction]:
    """Optional CSV: symbol,ex_date,factor,kind."""
    if not path.exists():
        return []
    out: list[CorpAction] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            ex = date.fromisoformat((row.get("ex_date") or row.get("date") or "").strip())
            factor = float(row.get("factor") or 1.0)
            kind = (row.get("kind") or "bonus").strip()
            out.append(CorpAction(symbol=sym, ex_date=ex, factor=factor, kind=kind))
    return out


def apply_corp_actions(df: pd.DataFrame, symbol: str, actions: list[CorpAction]) -> pd.DataFrame:
    """Adjust OHLC forward; store cumulative adj_factor per row (strategies use adjusted prices)."""
    if df.empty or not actions:
        out = df.copy()
        if "adj_factor" not in out.columns:
            out["adj_factor"] = 1.0
        return out
    out = df.copy()
    factors: list[float] = []
    for d_int in out["date"].astype(int):
        d = date(d_int // 10000, (d_int // 100) % 100, d_int % 100)
        f = adj_factor_on(symbol, d, actions)
        factors.append(f)
    out["adj_factor"] = factors
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col].astype(float) * out["adj_factor"]
    return out


@dataclass
class BuildStats:
    files_read: int
    files_skipped: int
    symbols: int
    rows_written: int
    corp_actions: int


def ingest_bhav_dir(
    lake: Lake,
    bhav_dir: Path,
    *,
    corp_actions: list[CorpAction] | None = None,
) -> BuildStats:
    """Read every bhav_YYYYMMDD.csv under bhav_dir, merge, apply corp actions, upsert lake."""
    corp_actions = corp_actions or []
    paths = sorted(bhav_dir.glob("bhav_*.csv"))
    if not paths:
        return BuildStats(0, 0, 0, 0, len(corp_actions))
    combined: pd.DataFrame | None = None
    read = 0
    skipped = 0
    for p in paths:
        if p.stat().st_size == 0:
            skipped += 1
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            part = parse_bhavcopy_csv(text)
        except (ValueError, OSError):
            skipped += 1
            continue
        if part.empty:
            skipped += 1
            continue
        combined = part if combined is None else pd.concat([combined, part], ignore_index=True)
        read += 1
    if combined is None or combined.empty:
        return BuildStats(read, skipped, 0, 0, len(corp_actions))
    combined = combined.drop_duplicates(["symbol", "date"], keep="last")
    counts: dict[str, int] = {}
    rows = 0
    for sym, part in combined.groupby("symbol"):
        cols = ["date", "open", "high", "low", "close", "volume", "delivery_qty", "source"]
        chunk = part[cols].copy()
        if "adj_factor" not in chunk.columns:
            chunk["adj_factor"] = 1.0
        adjusted = apply_corp_actions(chunk, str(sym), corp_actions)
        n = lake.write_daily(str(sym), adjusted)
        counts[str(sym)] = n
        rows += n
    return BuildStats(read, skipped, len(counts), rows, len(corp_actions))


def write_data_health_markdown(
    lake: Lake,
    *,
    symbols: list[str],
    out_path: Path,
    corp_actions_applied: bool,
    build: BuildStats | None = None,
) -> dict:
    """Summarise lake coverage for the owner (V-NEXT N1)."""
    from data.calendar import CalendarMissing
    from data.health import report_symbol, trading_day_gaps

    lines = [
        "# Data health report (auto-generated)",
        "",
        f"- Corporate actions applied: **{corp_actions_applied}**",
    ]
    if build:
        lines.extend(
            [
                f"- Bhav files read: {build.files_read} (skipped {build.files_skipped})",
                f"- Symbols in lake: {build.symbols}",
                f"- Corp action rows loaded: {build.corp_actions}",
            ]
        )
    lines.append("")
    lines.append("| symbol | daily_rows | from | to | gap_days |")
    lines.append("|---|---:|---|---|---:|")
    summary: dict = {"symbols": {}, "corp_actions_applied": corp_actions_applied}
    for sym in sorted(symbols):
        h = report_symbol(lake, sym)
        daily = lake.read_daily(sym)
        gaps: list[int] | None = []
        if h.history_from and h.history_to:
            try:
                gaps = trading_day_gaps(daily, h.history_from, h.history_to)
            except CalendarMissing:
                gaps = None
        gap_n = len(gaps) if gaps is not None else -1
        lines.append(f"| {sym} | {h.daily_rows} | {h.history_from} | {h.history_to} | {gap_n} |")
        summary["symbols"][sym] = {
            "daily_rows": h.daily_rows,
            "from": h.history_from,
            "to": h.history_to,
            "missing_trading_days": gap_n,
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
