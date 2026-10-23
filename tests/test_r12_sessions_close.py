"""R12: daily bar close ms from sessions.json (CAS vs continuous)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.sessions import daily_bar_close_ms
from core.types import Bar
from strategies.base import BarView

IST = ZoneInfo("Asia/Kolkata")


def test_fo_cas_close_1535_in_aug_2026():
    open_ms = int(datetime(2026, 8, 10, 9, 15, tzinfo=IST).timestamp() * 1000)
    close_ms = daily_bar_close_ms(open_ms, "fo")
    close_dt = datetime.fromtimestamp(close_ms / 1000, tz=IST)
    assert close_dt.hour == 15 and close_dt.minute == 35


def test_forming_daily_excluded_not_raised():
    open_ms = int(datetime(2026, 10, 23, 9, 15, tzinfo=IST).timestamp() * 1000)
    at_1400 = int(datetime(2026, 10, 23, 14, 0, tzinfo=IST).timestamp() * 1000)
    view = BarView(
        bars=[Bar(ts_ms=open_ms, open=1, high=1, low=1, close=1, volume=1)],
        decision_ms=at_1400,
        timeframe="1d",
    )
    assert view.closed() == []
