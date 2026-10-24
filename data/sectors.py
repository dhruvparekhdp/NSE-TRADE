"""NSE sector map from ind_nifty100list.csv (Industry column) — Book B sector cap."""

from __future__ import annotations

import csv
import io
from functools import lru_cache
from pathlib import Path


def parse_nifty100_sectors(text: str) -> dict[str, str]:
    """Return symbol -> Industry (uppercase trimmed)."""
    reader = csv.DictReader(io.StringIO(text))
    out: dict[str, str] = {}
    for row in reader:
        sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
        ind = (row.get("Industry") or row.get("industry") or "UNKNOWN").strip().upper()
        if sym:
            out[sym] = ind or "UNKNOWN"
    return out


@lru_cache(maxsize=1)
def load_sector_map(path: str | None = None) -> dict[str, str]:
    root = Path(__file__).resolve().parent.parent
    p = Path(path) if path else root / "config" / "ind_nifty100list.csv"
    if not p.exists():
        fix = root / "tests" / "fixtures" / "nse" / "nifty100.csv"
        if fix.exists():
            return parse_nifty100_sectors(fix.read_text(encoding="utf-8"))
        return {}
    return parse_nifty100_sectors(p.read_text(encoding="utf-8"))


def sector_for(symbol: str, sector_map: dict[str, str] | None = None) -> str:
    m = sector_map if sector_map is not None else load_sector_map()
    return m.get(symbol.upper(), "UNKNOWN")
