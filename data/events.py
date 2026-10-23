"""Calendar features: F&O expiry, MPC, budget, results proximity (PLAN_V2 V1-8)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from data.calendar import Calendar, load_default_calendar


def last_tuesday(year: int, month: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != 1:  # Tuesday
        d -= timedelta(days=1)
    return d


def fo_expiry_day(year: int, month: int, calendar: Calendar | None = None) -> date:
    """Last Tuesday of the month, moved back if a holiday/weekend."""
    cal = calendar or load_default_calendar()
    d = last_tuesday(year, month)
    while not cal.is_trading_day(d):
        d -= timedelta(days=1)
    return d


@lru_cache(maxsize=1)
def _mpc_budget(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy_dates(path: Path | None = None) -> dict:
    p = path or Path(__file__).resolve().parent.parent / "config" / "policy_dates.json"
    if not p.exists():
        return {"mpc": [], "budget": []}
    return _mpc_budget(str(p))


def is_mpc_day(d: date) -> bool:
    return d.isoformat() in set(load_policy_dates().get("mpc") or [])


def is_budget_day(d: date) -> bool:
    return d.isoformat() in set(load_policy_dates().get("budget") or [])


def is_expiry_day(d: date, calendar: Calendar | None = None) -> bool:
    return d == fo_expiry_day(d.year, d.month, calendar)


def results_in_days(d: date, results_dates: set[date] | None = None) -> int | None:
    """Days until next results date, or None if unknown."""
    if not results_dates:
        return None
    future = sorted(x for x in results_dates if x >= d)
    if not future:
        return None
    return (future[0] - d).days


def signal_features(
    d: date,
    *,
    results_dates: set[date] | None = None,
    calendar: Calendar | None = None,
) -> dict:
    return {
        "results_in_days": results_in_days(d, results_dates),
        "expiry_day": is_expiry_day(d, calendar),
        "mpc_day": is_mpc_day(d),
        "budget_day": is_budget_day(d),
    }
