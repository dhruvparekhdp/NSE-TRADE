"""P0-3: session states for normal day, holiday, Muhurat; IST maths."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.clock import SessionState, session_state, to_ist
from data.calendar import load_default_calendar

IST = ZoneInfo("Asia/Kolkata")


def _ms(y: int, m: int, d: int, hh: int, mm: int) -> int:
    dt = datetime(y, m, d, hh, mm, tzinfo=IST)
    return int(dt.timestamp() * 1000)


def test_weekend_is_holiday_or_closed():
    # Saturday 2026-10-24
    assert session_state(_ms(2026, 10, 24, 10, 0)) == SessionState.HOLIDAY


def test_known_holiday_republic_day():
    cal = load_default_calendar()
    assert cal.is_holiday(date(2026, 1, 26))
    assert session_state(_ms(2026, 1, 26, 10, 0)) == SessionState.HOLIDAY


def test_normal_day_session_transitions():
    # Wednesday 2026-10-21 (not a holiday) — F&O CAS regime (cont ends 15:15)
    assert session_state(_ms(2026, 10, 21, 8, 59)) == SessionState.CLOSED
    assert session_state(_ms(2026, 10, 21, 9, 0)) == SessionState.PRE_OPEN
    assert session_state(_ms(2026, 10, 21, 9, 15)) == SessionState.OPEN
    assert session_state(_ms(2026, 10, 21, 14, 45)) == SessionState.NO_NEW_ENTRIES
    assert session_state(_ms(2026, 10, 21, 15, 5)) == SessionState.SQUARE_OFF
    assert session_state(_ms(2026, 10, 21, 15, 20)) == SessionState.CLOSING_AUCTION
    assert session_state(_ms(2026, 10, 21, 15, 40)) == SessionState.CLOSED


def test_muhurat_special_session():
    # Sunday 2026-11-08 afternoon Muhurat (MARKET_INDIA §2)
    assert session_state(_ms(2026, 11, 8, 14, 30)) == SessionState.MUHURAT
    assert session_state(_ms(2026, 11, 8, 15, 10)) == SessionState.SQUARE_OFF
    assert session_state(_ms(2026, 11, 8, 12, 0)) == SessionState.CLOSED


def test_ist_round_trip_no_dst():
    ms = _ms(2026, 6, 15, 12, 0)
    dt = to_ist(ms)
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 5.5 * 3600
    assert dt.hour == 12
