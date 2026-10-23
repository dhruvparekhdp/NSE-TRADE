"""R6: context builder fills extras; S3/S3b/S4/S5 fire without hand-fed extras dict."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Bar
from lab.context import bars_for_strategy, build_intraday_context
from strategies.base import BarView
from strategies.gap import GapAndGo, GapFade
from strategies.intraday_momentum import AfternoonMomo
from strategies.pdh_rs import PDHRS

IST = ZoneInfo("Asia/Kolkata")


def _ms(h: int, m: int, day: int = 15) -> int:
    return int(datetime(2026, 10, day, h, m, tzinfo=IST).timestamp() * 1000)


def _bar(ts: int, o: float, h: float, lo: float, c: float, vol: int = 1000) -> Bar:
    return Bar(ts_ms=ts, open=o, high=h, low=lo, close=c, volume=vol)


def test_build_context_sets_gap_and_ranks():
    ctx = build_intraday_context(
        trade_date="2026-10-15",
        symbol="AAA",
        prev_close=100.0,
        pdh=102.0,
        open_px=103.0,
        decision_ms=_ms(10, 0),
        universe_session_rets={"AAA": 2.0, "BBB": 0.5, "CCC": -1.0},
    )
    assert ctx.extras["gap_pct"] == 3.0
    assert ctx.extras["pdh"] == 102.0
    assert ctx.extras["prev_close"] == 100.0
    assert ctx.extras["rs_rank"] == 1  # AAA strongest
    assert ctx.extras["ret_decile"] == 10


def test_s3_gapfade_fires_from_context():
    # Gap up 2%: open 102 vs prev 100; first 15m fades (close < open)
    bars = [_bar(_ms(9, 15 + i), 102.0, 102.5, 101.0, 101.2 if i == 14 else 102.0) for i in range(15)]
    bars += [_bar(_ms(9, 30 + i), 101.2, 101.5, 101.0, 101.1) for i in range(10)]
    ctx = build_intraday_context(
        trade_date="2026-10-15",
        symbol="X",
        prev_close=100.0,
        pdh=101.0,
        open_px=102.0,
        decision_ms=bars[-1].ts_ms + 60_000,
    )
    # Strategy expects ~1m bars for first-15 window; pass 1m
    view = BarView(bars=bars, decision_ms=bars[-1].ts_ms + 60_000, timeframe="1m")
    sigs = GapFade().on_bar("X", view, ctx)
    assert sigs and sigs[0].side == -1


def test_s3b_gapgo_fires_from_context():
    bars = [_bar(_ms(9, 15 + i), 102.0, 103.0, 101.8, 102.8 if i == 14 else 102.5) for i in range(15)]
    bars += [_bar(_ms(9, 30 + i), 102.8, 103.2, 102.5, 103.0) for i in range(10)]
    ctx = build_intraday_context(
        trade_date="2026-10-15",
        symbol="X",
        prev_close=100.0,
        pdh=101.0,
        open_px=102.0,
        decision_ms=bars[-1].ts_ms + 60_000,
    )
    view = BarView(bars=bars, decision_ms=bars[-1].ts_ms + 60_000, timeframe="1m")
    sigs = GapAndGo().on_bar("X", view, ctx)
    assert sigs and sigs[0].side == 1


def test_s4_momo_fires_from_context():
    bars: list[Bar] = []
    # Morning rally + afternoon above VWAP at 14:00
    px = 100.0
    for hm in range(9 * 60 + 15, 14 * 60 + 1):  # last bar 14:00 IST
        h, m = divmod(hm, 60)
        c = px * 1.001
        bars.append(_bar(_ms(h, m), px, c * 1.002, px * 0.999, c, vol=2000))
        px = c
    ctx = build_intraday_context(
        trade_date="2026-10-15",
        symbol="X",
        prev_close=100.0,
        pdh=101.0,
        open_px=100.5,
        decision_ms=bars[-1].ts_ms + 60_000,
        universe_session_rets={"X": 5.0, "Y": 0.0, "Z": -2.0},
    )
    assert ctx.extras["ret_decile"] >= 9
    view = BarView(bars=bars, decision_ms=bars[-1].ts_ms + 60_000, timeframe="1m")
    sigs = AfternoonMomo().on_bar("X", view, ctx)
    assert sigs


def test_s5_pdh_rs_fires_from_context():
    # Flat session then a gentle break above PDH 102 while staying near VWAP.
    bars: list[Bar] = []
    for hm in range(9 * 60 + 15, 10 * 60 + 30):
        h, m = divmod(hm, 60)
        bars.append(_bar(_ms(h, m), 101.0, 101.2, 100.8, 101.0, vol=2000))
    for hm in range(10 * 60 + 30, 11 * 60):
        h, m = divmod(hm, 60)
        bars.append(_bar(_ms(h, m), 102.2, 102.4, 102.0, 102.3, vol=2500))
    ctx = build_intraday_context(
        trade_date="2026-10-15",
        symbol="X",
        prev_close=100.0,
        pdh=102.0,
        open_px=100.5,
        decision_ms=bars[-1].ts_ms + 60_000,
        universe_session_rets={"X": 3.0, "Y": 1.0, "Z": 0.0},
    )
    assert ctx.extras["rs_rank"] == 1
    view = BarView(bars=bars, decision_ms=bars[-1].ts_ms + 60_000, timeframe="1m")
    sigs = PDHRS().on_bar("X", view, ctx)
    assert sigs and sigs[0].side == 1


def test_resample_5m_for_strategy():
    bars = [_bar(_ms(9, 15 + i), 100, 101, 99, 100.5) for i in range(10)]
    rs = bars_for_strategy(bars, "5m")
    assert len(rs) == 2
    assert rs[0].volume == sum(b.volume for b in bars[:5])
