"""IST clock and session state machine (plan A9.1 + PLAN_V2 V1-1). Injectable for tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from data.calendar import Calendar, load_default_calendar

IST = ZoneInfo("Asia/Kolkata")
UTC = UTC
_SESSIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "sessions.json"


class SessionState(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    NO_NEW_ENTRIES = "NO_NEW_ENTRIES"
    SQUARE_OFF = "SQUARE_OFF"
    CLOSING_AUCTION = "CLOSING_AUCTION"
    POST_CLOSE = "POST_CLOSE"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"
    MUHURAT = "MUHURAT"
    SPECIAL = "SPECIAL"


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


@lru_cache(maxsize=1)
def _regimes() -> list[dict]:
    return list(json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))["regimes"])


def _in_range(d: date, start: str, end: str | None) -> bool:
    if d < date.fromisoformat(start):
        return False
    if end is None:
        return True
    return d <= date.fromisoformat(end)


def regime_for(d: date, stock_class: str = "fo") -> dict | None:
    """Dated session regime for a stock class (fo / non_fo)."""
    sc = "fo" if stock_class in {"fo", "FO", "fno"} else "non_fo"
    for row in _regimes():
        if row.get("class") != sc:
            continue
        if _in_range(d, row["from"], row.get("to")):
            return row
    return None


def session_state(
    ms: int,
    *,
    calendar: Calendar | None = None,
    stock_class: str = "fo",
    no_entry_after: str = "14:45",
    square_off_at: str = "15:05",
    market_open: str = "09:15",
    market_close: str = "15:30",
    pre_open: str = "09:00",
) -> SessionState:
    """Return session state for a UTC epoch-ms instant (PLAN_V2 V1-1).

    `stock_class` selects the dated CAS/continuous regime. Engine square-off /
    no-entry overlays apply only while continuous trading is open.
    """
    cal = calendar or load_default_calendar()
    dt = to_ist(ms)
    d = dt.date()
    t = dt.timetz().replace(tzinfo=None)

    special = cal.special_session(d)
    if special is not None:
        open_t = _parse_hhmm(special.open)
        close_t = _parse_hhmm(special.close)
        sq = _parse_hhmm(special.square_off_at or square_off_at)
        if t < open_t or t >= close_t:
            return SessionState.CLOSED
        if t >= sq:
            return SessionState.SQUARE_OFF
        # Whole Muhurat/special window is one state (no new entries is a setting, V1-2)
        return SessionState.MUHURAT

    if not cal.is_trading_day(d):
        return SessionState.HOLIDAY if cal.is_holiday(d) or d.weekday() >= 5 else SessionState.CLOSED

    reg = regime_for(d, stock_class)
    if reg is None:
        # legacy fallback
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

    pre_lo, pre_hi = reg["pre_open"][0]
    pre_start, pre_end = _parse_hhmm(pre_lo), _parse_hhmm(pre_hi)
    cont_lo, cont_hi = reg["continuous"]
    cont_start, cont_end = _parse_hhmm(cont_lo), _parse_hhmm(cont_hi)
    cas = reg.get("cas")
    post = reg.get("post_close")
    post_start = post_end = None
    if post:
        post_start, post_end = _parse_hhmm(post[0]), _parse_hhmm(post[1])

    if t < pre_start:
        return SessionState.CLOSED
    if pre_start <= t < pre_end:
        return SessionState.PRE_OPEN
    if cont_start <= t < cont_end:
        no_entry = _parse_hhmm(no_entry_after)
        sq = _parse_hhmm(square_off_at)
        if t >= sq:
            return SessionState.SQUARE_OFF
        if t >= no_entry:
            return SessionState.NO_NEW_ENTRIES
        return SessionState.OPEN
    if cas:
        cas_start, cas_end = _parse_hhmm(cas["start"]), _parse_hhmm(cas["end"])
        if cas_start <= t < cas_end:
            return SessionState.CLOSING_AUCTION
    if post_start is not None and post_end is not None and post_start <= t < post_end:
        return SessionState.POST_CLOSE
    return SessionState.CLOSED
