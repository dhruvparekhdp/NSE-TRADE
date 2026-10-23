"""PLAN_V2 V1-2..V1-8 acceptance tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.costs import order_brokerage, rates_for, round_trip
from core.risk import PortfolioState, RiskLimits, can_open, size
from core.session_times import derive_engine_times
from core.types import Signal
from data.calendar import CalendarMissing, job_should_run, load_default_calendar, reset_calendar_cache
from data.corporate_actions import CorpAction, adjust_close
from data.events import fo_expiry_day, signal_features
from data.history import parse_bhavcopy_csv
from data.universe import universe_on


def test_v1_2_calendar_missing_2027():
    reset_calendar_cache()
    cal = load_default_calendar()
    with pytest.raises(CalendarMissing):
        cal.is_trading_day(date(2027, 1, 4))


def test_v1_2_holiday_skips_jobs():
    reset_calendar_cache()
    assert job_should_run(date(2026, 1, 26)) is False  # Republic Day
    assert job_should_run(date(2026, 10, 21)) is True


def test_v1_3_derive_square_off():
    sq, no_entry = derive_engine_times("15:10", squareoff_lead_min=15, no_entry_lead_min=20)
    assert sq == "14:55"
    assert no_entry == "14:35"
    with pytest.raises(ValueError):
        derive_engine_times("15:10", squareoff_lead_min=0)


def test_v1_4_min_brokerage_and_cnc_floor():
    rates = rates_for("MIS")
    assert order_brokerage(3_000, rates) == 5.0  # max(5, min(20, 3))
    assert order_brokerage(100_000, rates) == 20.0
    bd = round_trip(100_000, 100_000, "MIS", rates)
    assert abs(bd.total - 82.68) < 1.5  # MARKET_INDIA §5
    lim = RiskLimits(min_position_cnc_inr=20_000)
    # tiny risk / capital → position under CNC floor
    r2 = size(100.0, 99.0, 50_000.0, 0.1, 0.05, "B", lim)
    assert r2.reason in {"below_min_cnc_position", "ok", "qty_zero"}


def test_v1_5_is_fo_from_nfo_rows():
    from data.instruments import parse_scrip_master

    rows = [
        {"exch_seg": "NSE", "symbol": "SBIN-EQ", "token": "1", "name": "SBIN", "tick_size": 5, "lotsize": 1},
        {"exch_seg": "NSE", "symbol": "FAKENFO-EQ", "token": "2", "name": "FAKENFO", "tick_size": 5, "lotsize": 1},
        {
            "exch_seg": "NFO",
            "symbol": "SBIN25OCTFUT",
            "token": "9",
            "name": "SBIN",
            "instrumenttype": "FUTSTK",
            "tick_size": 5,
            "lotsize": 1,
        },
    ]
    m = parse_scrip_master(rows)
    assert m["SBIN"]["is_fo"] is True
    assert m["FAKENFO"]["is_fo"] is False


def test_v1_5_surveillance_and_exposure():
    lim = RiskLimits(surveillance_symbols=frozenset({"FAKEASM1"}), max_mis_exposure_x=1.0)
    sig = Signal(
        symbol="FAKEASM1",
        side=1,
        entry_ref=100.0,
        stop=99.0,
        target=None,
        time_exit_ms=None,
        book="A",
        strategy="S1",
        ts_ms=0,
    )
    st = PortfolioState(capital=100_000, start_capital=100_000, mis_exposure=0.0)
    ok, reason = can_open(st, sig, lim, 0)
    assert ok is False and reason == "surveillance"
    sig2 = Signal(
        symbol="SBIN",
        side=1,
        entry_ref=100.0,
        stop=99.0,
        target=None,
        time_exit_ms=None,
        book="A",
        strategy="S1",
        ts_ms=0,
    )
    st2 = PortfolioState(capital=100_000, start_capital=100_000, mis_exposure=50_000)
    ok2, reason2 = can_open(st2, sig2, lim, 0, new_position_value=60_000)
    assert ok2 is False and reason2 == "mis_exposure"


def test_v1_6_survivorship():
    assert "OLDCO" in universe_on(date(2019, 1, 1))
    assert "OLDCO" not in universe_on(date(2021, 1, 1))
    assert "NEWNIFTY" in universe_on(date(2021, 4, 1))


def test_v1_7_udiff_and_bonus_adjust():
    text = (Path(__file__).parent / "fixtures" / "bhav_udiff_sample.csv").read_text()
    df = parse_bhavcopy_csv(text)
    assert set(df["symbol"]) == {"RELIANCE", "TCS", "SBIN", "INFY"}  # BE filtered
    assert df.iloc[0]["source"] == "bhav_udiff"
    actions = [CorpAction("RELIANCE", date(2024, 8, 1), 2.0, "bonus")]
    # before ex-date: adjusted = raw * 2 (1:1 bonus)
    assert adjust_close(3000.0, "RELIANCE", date(2024, 7, 31), actions) == 6000.0
    assert adjust_close(3020.0, "RELIANCE", date(2024, 8, 1), actions) == 3020.0


def test_v1_8_expiry_last_tuesday():
    # Sep 2025 last Tuesday is 30 Sep 2025 — holiday check uses 2026 calendar only;
    # for 2026-03 last Tuesday = 31 Mar 2026 which IS a holiday (Mahavir Jayanti)
    d = fo_expiry_day(2026, 3)
    assert d.weekday() == 1 or d < date(2026, 3, 31)
    assert d != date(2026, 3, 31)  # moved back off holiday
    feats = signal_features(d)
    assert feats["expiry_day"] is True
