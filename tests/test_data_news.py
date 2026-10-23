"""Lake, bhav, instruments, bars, news sentiment, Angel guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from broker.angel import AngelBroker
from broker.errors import RateLimited, Rejected
from data.bars import BarBuilder, Tick, resample
from data.history import angel_candles_to_df, ingest_bhav_to_lake, parse_bhavcopy_csv, window_30d
from data.instruments import load_universe_from_fixtures
from data.lake import Lake
from news.foreign import build_snapshot
from news.sentiment import score_headlines

FIX = Path(__file__).parent / "fixtures"


def test_bhav_and_lake(tmp_path):
    text = (FIX / "nse" / "bhav_sample.csv").read_text()
    df = parse_bhavcopy_csv(text)
    lake = Lake(tmp_path / "lake")
    counts = ingest_bhav_to_lake(lake, df)
    assert counts["SBIN"] >= 2
    again = ingest_bhav_to_lake(lake, df)
    assert again["SBIN"] == counts["SBIN"]  # deduped


def test_universe_join_reports_missing():
    mapped, missing = load_universe_from_fixtures(FIX / "nse")
    assert len(mapped) >= 5
    # NIFTY row without -EQ should not map as equity
    assert isinstance(missing, list)


def test_bars_late_and_resample():
    bb = BarBuilder()
    base = 1_700_000_000_000
    # first minute
    bb.on_tick(Tick("SBIN", base + 10_000, 100, 1000), now_ms=base + 10_000)
    # late tick into previous minute
    closed = bb.on_tick(Tick("SBIN", base + 50_000, 101, 1100), now_ms=base + 65_000)
    assert closed  # rolled
    bars = bb.flush("SBIN")
    rs = resample(closed + bars, 5)
    assert rs


def test_news_composite_bearish():
    snap, score = build_snapshot(
        trade_date="2026-10-23",
        us_close_yesterday=100,
        us_close_day_before=103,
        fii_net_cr=-3000,
        headlines=["Market crash after fraud raid"],
        results_window=True,
    )
    assert score < 0
    assert score_headlines(["Record rally upgrade"]) > 0


def test_angel_live_guard_and_rate_limit():
    class Fake:
        def placeOrder(self, *_a, **_k):
            return {"status": True, "data": {"orderid": "1"}}

        def getCandleData(self, *_a, **_k):
            return {"status": False, "errorcode": "AB1021", "message": "too many requests"}

    broker = AngelBroker(api=Fake(), sleep=lambda _s: None)
    with pytest.raises(Rejected):
        broker.place_order({"tradingsymbol": "SBIN-EQ"})

    with pytest.raises(RateLimited):
        broker.candles({})


def test_angel_candle_parse():
    import json

    raw = json.loads((FIX / "angel" / "candles_sbin.json").read_text())
    df = angel_candles_to_df(raw["data"])
    assert len(df) == 2 and "ts_ms" in df.columns


def test_window_maths():
    from datetime import date

    w = window_30d(date(2024, 1, 1), date(2024, 3, 1))
    assert len(w) >= 2
