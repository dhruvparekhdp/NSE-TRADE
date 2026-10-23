"""Nifty 100 universe + Angel token map (plan P1-1). Network optional; fixtures for tests."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

# Seed list (subset for tests + offline). Full 100 loaded from CSV fixture / live NSE.
NIFTY100_SEED = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "ICICIBANK",
    "HINDUNILVR",
    "ITC",
    "SBIN",
    "BHARTIARTL",
    "KOTAKBANK",
    "LT",
    "AXISBANK",
    "BAJFINANCE",
    "ASIANPAINT",
    "MARUTI",
    "SUNPHARMA",
    "TITAN",
    "WIPRO",
    "ULTRACEMCO",
    "NESTLEIND",
]


def parse_nifty100_csv(text: str) -> list[str]:
    reader = csv.DictReader(io.StringIO(text))
    syms = []
    for row in reader:
        # NSE file uses 'Symbol'
        s = (row.get("Symbol") or row.get("symbol") or "").strip()
        if s:
            syms.append(s.upper())
    return syms


def parse_scrip_master(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Filter NSE -EQ rows into symbol -> token/tick map. tick_size in paise → rupees."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if str(r.get("exch_seg", "")).upper() != "NSE":
            continue
        sym = str(r.get("symbol") or "")
        if not sym.endswith("-EQ"):
            continue
        name = sym[: -len("-EQ")]
        tick_paise = float(r.get("tick_size") or 5)
        out[name] = {
            "symbol": name,
            "token": str(r.get("token") or ""),
            "trading_symbol": sym,
            "name": str(r.get("name") or name),
            "tick_size": tick_paise / 100.0 if tick_paise >= 1 else tick_paise,
            "lot_size": int(r.get("lotsize") or 1),
        }
    return out


def build_universe(
    nifty_symbols: list[str],
    scrip_map: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Join Nifty 100 with Angel tokens. Missing symbols listed, not dropped silently."""
    mapped = []
    missing = []
    for s in nifty_symbols:
        row = scrip_map.get(s)
        if row is None:
            missing.append(s)
            continue
        mapped.append({**row, "in_universe": 1})
    return mapped, missing


def load_universe_from_fixtures(fixtures_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    nifty_path = fixtures_dir / "nifty100.csv"
    scrip_path = fixtures_dir / "scrip_master_sample.json"
    if nifty_path.exists():
        syms = parse_nifty100_csv(nifty_path.read_text(encoding="utf-8"))
    else:
        syms = list(NIFTY100_SEED)
    if scrip_path.exists():
        rows = json.loads(scrip_path.read_text(encoding="utf-8"))
    else:
        rows = [
            {
                "exch_seg": "NSE",
                "symbol": f"{s}-EQ",
                "token": str(1000 + i),
                "name": s,
                "tick_size": 5,
                "lotsize": 1,
            }
            for i, s in enumerate(syms)
        ]
    return build_universe(syms, parse_scrip_master(rows))
