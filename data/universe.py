"""Survivorship-aware Nifty membership (PLAN_V2 V1-6)."""

from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
from pathlib import Path

from data.instruments import NIFTY100_SEED


@lru_cache(maxsize=1)
def _events(path: str) -> list[tuple[date, str, str]]:
    rows: list[tuple[date, str, str]] = []
    with Path(path).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((date.fromisoformat(row["date"]), row["symbol"].upper(), row["action"].lower()))
    rows.sort(key=lambda r: r[0])
    return rows


def universe_on(d: date, *, history_path: Path | None = None) -> set[str]:
    """Symbols in the universe on date `d` after applying add/remove history."""
    path = history_path or Path(__file__).resolve().parent.parent / "config" / "universe_history.csv"
    if not path.exists():
        return set(NIFTY100_SEED)
    members: set[str] = set()
    for when, sym, action in _events(str(path)):
        if when > d:
            break
        if action == "add":
            members.add(sym)
        elif action == "remove":
            members.discard(sym)
    return members
