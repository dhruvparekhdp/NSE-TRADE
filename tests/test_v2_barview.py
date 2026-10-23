"""V2-3 / B13: BarView knows the timeframe; daily bars are not closed at +60s."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Bar
from strategies.base import BarView

IST = ZoneInfo("Asia/Kolkata")


def _daily(ts_ms: int) -> Bar:
    return Bar(ts_ms=ts_ms, open=100, high=101, low=99, close=100.5, volume=1)


def test_daily_bar_not_visible_at_1400_same_day():
    open_ms = int(datetime(2026, 10, 23, 9, 15, tzinfo=IST).timestamp() * 1000)
    at_1400 = int(datetime(2026, 10, 23, 14, 0, tzinfo=IST).timestamp() * 1000)
    view = BarView(bars=[_daily(open_ms)], decision_ms=at_1400, timeframe="1d")
    assert view.closed() == []


def test_daily_bar_visible_after_session():
    open_ms = int(datetime(2026, 10, 23, 9, 15, tzinfo=IST).timestamp() * 1000)
    at_1600 = int(datetime(2026, 10, 23, 16, 0, tzinfo=IST).timestamp() * 1000)
    view = BarView(bars=[_daily(open_ms)], decision_ms=at_1600, timeframe="1d")
    assert len(view.closed()) == 1


def test_1m_bar_still_closes_after_60s():
    ts = 1_000_000
    view = BarView(
        bars=[Bar(ts_ms=ts, open=1, high=1, low=1, close=1, volume=1)],
        decision_ms=ts + 60_000,
        timeframe="1m",
    )
    assert len(view.closed()) == 1
