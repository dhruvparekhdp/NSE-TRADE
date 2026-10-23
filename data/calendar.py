"""NSE trading calendar from yearly holiday JSON (plan A5 / P0-3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class SpecialSession:
    date: date
    name: str
    open: str
    close: str
    no_entry_after: str | None = None
    square_off_at: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Calendar:
    holidays: frozenset[date]
    holiday_names: dict[date, str]
    special_sessions: dict[date, SpecialSession]

    def is_holiday(self, d: date) -> bool:
        return d in self.holidays

    def is_weekend(self, d: date) -> bool:
        return d.weekday() >= 5

    def is_trading_day(self, d: date) -> bool:
        if d in self.special_sessions:
            return True
        if self.is_weekend(d) or self.is_holiday(d):
            return False
        return True

    def special_session(self, d: date) -> SpecialSession | None:
        return self.special_sessions.get(d)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_calendar(path: Path) -> Calendar:
    raw = json.loads(path.read_text(encoding="utf-8"))
    holidays: set[date] = set()
    names: dict[date, str] = {}
    for row in raw.get("holidays", []):
        d = _parse_date(row["date"])
        holidays.add(d)
        names[d] = row.get("name", "")
    special: dict[date, SpecialSession] = {}
    for row in raw.get("special_sessions", []):
        d = _parse_date(row["date"])
        special[d] = SpecialSession(
            date=d,
            name=row.get("name", ""),
            open=row["open"],
            close=row["close"],
            no_entry_after=row.get("no_entry_after"),
            square_off_at=row.get("square_off_at"),
            note=row.get("note", ""),
        )
    return Calendar(
        holidays=frozenset(holidays),
        holiday_names=names,
        special_sessions=special,
    )


@lru_cache(maxsize=1)
def load_default_calendar() -> Calendar:
    path = Path(__file__).resolve().parent.parent / "config" / "holidays_2026.json"
    return load_calendar(path)


def next_trading_day(d: date, calendar: Calendar | None = None) -> date:
    cal = calendar or load_default_calendar()
    cur = datetime.combine(d, datetime.min.time()).date()
    # step forward
    from datetime import timedelta

    cur = cur + timedelta(days=1)
    while not cal.is_trading_day(cur):
        cur = cur + timedelta(days=1)
    return cur
