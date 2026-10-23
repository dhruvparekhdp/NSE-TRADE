"""IST clock and session state machine (plan A9.1). Injectable for tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

from data.calendar import Calendar, load_default_calendar

IST = ZoneInfo("Asia/Kolkata")
UTC = UTC


class SessionState(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    NO_NEW_ENTRIES = "NO_NEW_ENTRIES"
    SQUARE_OFF = "SQUARE_OFF"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"
    MUHURAT = "MUHURAT"


@dataclass(frozen=True)
class Clock:
    """Injectable clock. `now_ms` is UTC epoch milliseconds."""

    _now_ms: int | None = None

    def now_ms(self) -> int:
        if self._now_ms is not None:
            return self._now_ms
        return int(datetime.now(tz=UTC).timestamp() * 1000)

    def with_now(self, ms: int) -> Clock:
        return Clock(_now_ms=ms)


def to_ist(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).astimezone(IST)


def ist_today(ms: int | None = None, clock: Clock | None = None) -> date:
    c = clock or Clock()
    return to_ist(ms if ms is not None else c.now_ms()).date()


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def session_state(
    ms: int,
    *,
    calendar: Calendar | None = None,
    no_entry_after: str = "14:45",
    square_off_at: str = "15:05",
    market_open: str = "09:15",
    market_close: str = "15:30",
    pre_open: str = "09:00",
) -> SessionState:
    """Return session state for a UTC epoch-ms instant (plan A9.1 / A12)."""
    cal = calendar or load_default_calendar()
    dt = to_ist(ms)
    d = dt.date()
    t = dt.timetz().replace(tzinfo=None)

    special = cal.special_session(d)
    if special is not None:
        open_t = _parse_hhmm(special.open)
        close_t = _parse_hhmm(special.close)
        no_entry = _parse_hhmm(special.no_entry_after or no_entry_after)
        sq = _parse_hhmm(special.square_off_at or square_off_at)
        if t < open_t or t >= close_t:
            return SessionState.CLOSED
        if t >= sq:
            return SessionState.SQUARE_OFF
        if t >= no_entry:
            return SessionState.NO_NEW_ENTRIES
        return SessionState.MUHURAT

    if not cal.is_trading_day(d):
        return SessionState.HOLIDAY if cal.is_holiday(d) or d.weekday() >= 5 else SessionState.CLOSED

    pre = _parse_hhmm(pre_open)
    open_t = _parse_hhmm(market_open)
    close_t = _parse_hhmm(market_close)
    no_entry = _parse_hhmm(no_entry_after)
    sq = _parse_hhmm(square_off_at)

    if t < pre or t >= close_t:
        return SessionState.CLOSED
    if pre <= t < open_t:
        return SessionState.PRE_OPEN
    if t >= sq:
        return SessionState.SQUARE_OFF
    if t >= no_entry:
        return SessionState.NO_NEW_ENTRIES
    return SessionState.OPEN
