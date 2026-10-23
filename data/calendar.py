"""NSE trading calendar from yearly holiday JSON (plan A5 / PLAN_V2 V1-2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path


class CalendarMissing(Exception):
    """Raised when a year has no holidays_YYYY.json — refuse to invent trading days."""

    def __init__(self, year: int) -> None:
        self.year = year
        super().__init__(f"no holiday file for {year}; add config/holidays_{year}.json")


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
    years_loaded: frozenset[int]

    def require_year(self, year: int) -> None:
        if year not in self.years_loaded:
            raise CalendarMissing(year)

    def is_holiday(self, d: date) -> bool:
        self.require_year(d.year)
        return d in self.holidays

    def is_weekend(self, d: date) -> bool:
        return d.weekday() >= 5

    def is_trading_day(self, d: date) -> bool:
        self.require_year(d.year)
        if d in self.special_sessions:
            return True
        if self.is_weekend(d) or d in self.holidays:
            return False
        return True

    def special_session(self, d: date) -> SpecialSession | None:
        self.require_year(d.year)
        return self.special_sessions.get(d)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_calendar(path: Path) -> Calendar:
    raw = json.loads(path.read_text(encoding="utf-8"))
    year = int(raw.get("year") or path.stem.split("_")[-1])
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
        years_loaded=frozenset({year}),
    )


def _merge(cals: list[Calendar]) -> Calendar:
    holidays: set[date] = set()
    names: dict[date, str] = {}
    special: dict[date, SpecialSession] = {}
    years: set[int] = set()
    for c in cals:
        holidays |= set(c.holidays)
        names.update(c.holiday_names)
        special.update(c.special_sessions)
        years |= set(c.years_loaded)
    return Calendar(
        holidays=frozenset(holidays),
        holiday_names=names,
        special_sessions=special,
        years_loaded=frozenset(years),
    )


@lru_cache(maxsize=1)
def load_default_calendar() -> Calendar:
    """Load every config/holidays_*.json found."""
    cfg = Path(__file__).resolve().parent.parent / "config"
    paths = sorted(cfg.glob("holidays_*.json"))
    if not paths:
        raise CalendarMissing(0)
    return _merge([load_calendar(p) for p in paths])


def reset_calendar_cache() -> None:
    load_default_calendar.cache_clear()


def next_trading_day(d: date, calendar: Calendar | None = None) -> date:
    cal = calendar or load_default_calendar()
    cur = d + timedelta(days=1)
    while True:
        cal.require_year(cur.year)
        if cal.is_trading_day(cur):
            return cur
        cur = cur + timedelta(days=1)


def job_should_run(d: date | None = None, calendar: Calendar | None = None) -> bool:
    """Trading jobs skip holidays / weekends / missing calendar years."""
    cal = calendar or load_default_calendar()
    day = d or datetime.now().date()
    try:
        return cal.is_trading_day(day)
    except CalendarMissing:
        return False
