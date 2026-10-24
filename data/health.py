"""Data-quality checks (plan P1-7)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data.calendar import Calendar, CalendarMissing, load_default_calendar
from data.lake import Lake


@dataclass
class SymbolHealth:
    symbol: str
    daily_rows: int
    minute_rows: int
    missing_minutes_today: int
    last_ts_ms: int | None
    history_from: int | None
    history_to: int | None


def missing_minutes(ts_ms_list: list[int], session_minutes: list[int]) -> int:
    have = set(ts_ms_list)
    return sum(1 for m in session_minutes if m not in have)


def ist_session_minutes(day_open_ms: int, n: int = 375) -> list[int]:
    """09:15–15:29 inclusive ≈ 375 minutes."""
    return [day_open_ms + i * 60_000 for i in range(n)]


def report_symbol(lake: Lake, symbol: str) -> SymbolHealth:
    daily = lake.read_daily(symbol)
    mins = lake.read_minutes(symbol)
    last = int(mins["ts_ms"].iloc[-1]) if len(mins) else None
    return SymbolHealth(
        symbol=symbol,
        daily_rows=len(daily),
        minute_rows=len(mins),
        missing_minutes_today=0,
        last_ts_ms=last,
        history_from=int(daily["date"].iloc[0]) if len(daily) else None,
        history_to=int(daily["date"].iloc[-1]) if len(daily) else None,
    )


def trading_day_gaps(daily: pd.DataFrame, start: int, end: int, calendar: Calendar | None = None) -> list[int]:
    """Return YYYYMMDD trading days in [start,end] missing from daily frame."""
    from datetime import date, timedelta

    cal = calendar or load_default_calendar()
    have = set(int(x) for x in daily["date"].tolist()) if len(daily) else set()
    s = date(start // 10000, (start // 100) % 100, start % 100)
    e = date(end // 10000, (end // 100) % 100, end % 100)
    missing = []
    cur = s
    while cur <= e:
        try:
            trading = cal.is_trading_day(cur)
        except CalendarMissing:
            trading = cur.weekday() < 5
        if trading:
            key = int(cur.strftime("%Y%m%d"))
            if key not in have:
                missing.append(key)
        cur += timedelta(days=1)
    return missing
