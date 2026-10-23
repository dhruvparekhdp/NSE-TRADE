"""Session regime helpers — daily bar close from sessions.json (R12 / MARKET_INDIA §2)."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_CONFIG = Path(__file__).resolve().parent.parent / "config" / "sessions.json"


@lru_cache(maxsize=1)
def _load_regimes() -> list[dict[str, Any]]:
    data = json.loads(_CONFIG.read_text(encoding="utf-8"))
    return list(data.get("regimes") or [])


def regime_for(d: date, asset_class: str = "fo") -> dict[str, Any]:
    for row in _load_regimes():
        if row.get("class") != asset_class:
            continue
        start = date.fromisoformat(str(row["from"]))
        end_s = row.get("to")
        end = date.fromisoformat(end_s) if end_s else date.max
        if start <= d <= end:
            return row
    # fallback: standard continuous close
    return {"continuous": ["09:15", "15:30"], "cas": None}


def daily_bar_close_ms(bar_open_ms: int, asset_class: str = "fo") -> int:
    """UTC ms when the daily bar is considered closed (CAS end or continuous end)."""
    open_dt = datetime.fromtimestamp(bar_open_ms / 1000.0, tz=IST)
    d = open_dt.date()
    reg = regime_for(d, asset_class)
    cas = reg.get("cas")
    if isinstance(cas, dict) and cas.get("end"):
        hhmm = str(cas["end"])
    else:
        cont = reg.get("continuous") or ["09:15", "15:30"]
        hhmm = str(cont[1])
    h, m = map(int, hhmm.split(":"))
    close_dt = datetime(d.year, d.month, d.day, h, m, tzinfo=IST)
    return int(close_dt.timestamp() * 1000)
