"""V2-1 (B3/B4): daily fills, gap stops, trailing stop, 20-session exit (PLAN_V2 §3.3 probes)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.risk import RiskLimits
from core.types import Bar, Signal
from lab.backtest import run_daily_book
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")
D0 = date(2026, 3, 2)  # a Monday


def day_bar(i: int, o: float, h: float, lo: float, c: float, vol: int = 1_000_000) -> Bar:
    d = D0 + timedelta(days=i)
    ts = int(datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST).timestamp() * 1000)
    return Bar(ts_ms=ts, open=o, high=h, low=lo, close=c, volume=vol)


class OneShot:
    """Test strategy: emits one long signal at the close of bar `at`."""

    id = "S6_swing"
    book = "B"
    timeframe = "1d"

    def __init__(self, at: int, entry_ref: float = 100.0, stop: float = 98.1) -> None:
        self.at, self.entry_ref, self.stop = at, entry_ref, stop

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        last = bars.closed()[-1]
        if last.ts_ms != day_bar(self.at, 1, 1, 1, 1).ts_ms:
            return []
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=self.entry_ref,
                stop=self.stop,
                target=None,
                time_exit_ms=None,
                features={"atr14": 0.76},
                strategy=self.id,
                book="B",
            )
        ]


# max_open_swing=1 so the CNC slot is full capital (else slot/entry floors under ₹20k)
LIMITS = RiskLimits(max_open_swing=1)


def run(bars: list[Bar], at: int = 0, **kw):
    return run_daily_book(
        symbol="SBIN", daily_bars=bars, strategy=OneShot(at, **kw), capital=100_000.0, limits=LIMITS
    )


def flat(i: int, px: float = 100.0) -> Bar:
    return day_bar(i, px, px + 0.5, px - 0.5, px)


def test_gap_down_stop_fills_at_open_not_at_stop():
    """B3 probe: a -20% gap used to book -1.46R; the real fill is the open, about -10.6R."""
    bars = [
        flat(0),
        day_bar(1, 99.5, 100.0, 99.0, 99.6),  # entry day: limit 100.0 touched, opens below it
        day_bar(2, 80.0, 81.0, 79.0, 80.5),  # gaps 20% below the 98.1 stop
    ]
    bt = run(bars)
    assert len(bt.trades) == 1
    t = bt.trades[0]
    assert t.exit_reason == "stop_gap"
    assert abs(t.exit_price - 80.0 * (1 - 0.001)) < 0.02  # open − 0.05% slip − 0.05% stop extra
    # Entry improved to the open (99.5), so R is steeper than the classic −10.6 (entry-at-limit) figure
    assert t.r_mult < -10.0
    # Still far worse than the old bug that filled the stop at 98.1 (−1.46R)
    assert t.r_mult < -5.0


def test_stop_inside_the_day_fills_at_stop_with_slippage_and_extra():
    bars = [
        flat(0),
        day_bar(1, 99.5, 100.0, 99.0, 99.6),
        day_bar(2, 99.0, 99.5, 97.0, 97.5),  # opens above the stop, trades through 98.1
    ]
    t = run(bars).trades[0]
    assert t.exit_reason == "stop"
    assert abs(t.exit_price - 98.1 * (1 - 0.001)) < 0.02
    assert -1.8 < t.r_mult < -1.0


def test_next_day_limit_not_reached_is_no_fill():
    """B4: the day never trades down to the limit, so no entry is booked."""
    bars = [flat(0), day_bar(1, 103.0, 104.0, 102.0, 103.5), flat(2, 103.5)]
    bt = run(bars)
    assert bt.trades == []
    assert len(bt.no_fills) == 1


def test_opening_below_the_limit_fills_at_the_open_and_entry_ms_is_fill_day():
    bars = [flat(0), day_bar(1, 98.0, 99.0, 97.9, 98.5), flat(2, 98.5)]
    bt = run(bars)
    t = bt.trades[0]
    assert abs(t.entry_price - 98.0 * 1.0005) < 0.02  # open (better than the 100.0 limit) + 0.05% slip
    assert t.entry_ms == bars[1].ts_ms  # fill day 09:15 IST, not the signal day
    assert t.entry_ms != bars[0].ts_ms


def test_limit_touched_later_in_the_day_fills_at_the_limit():
    bars = [flat(0), day_bar(1, 101.0, 101.5, 99.9, 100.5), flat(2, 100.5)]
    t = run(bars).trades[0]
    assert abs(t.entry_price - 100.0 * 1.0005) < 0.02


def test_trailing_stop_ratchets_up_and_is_never_lowered():
    from core.exits import ExitRules, Position, step_exits

    rules = ExitRules(product="CNC", slippage_pct=0.05, stop_extra_slip_pct=0.05, trail_atr_mult=2.5, max_sessions=20)
    pos = Position(
        symbol="SBIN", strategy="S6_swing", book="B", side=1, qty=100, entry_ms=0,
        entry_price=100.0, stop_init=95.0, stop=95.0, risk_inr=500.0,
    )
    pos, ev = step_exits(pos, day_bar(1, 109, 111, 108, 110), rules, atr=2.0)
    assert ev is None and pos.stop == 105.0  # 110 - 2.5 * 2
    pos, ev = step_exits(pos, day_bar(2, 110, 110.5, 106, 107), rules, atr=4.0)
    assert ev is None and pos.stop == 105.0  # ATR doubled but the stop does not drop
    stops = [pos.stop]
    for k, c in enumerate([108, 111, 109], start=3):
        pos, ev = step_exits(pos, day_bar(k, c, c + 0.5, c - 0.5, c), rules, atr=1.0)
        stops.append(pos.stop)
    assert stops == sorted(stops)
    assert pos.stop == 111 - 2.5


def test_twenty_session_time_exit_at_the_close():
    bars = [flat(0), day_bar(1, 99.5, 100.2, 99.4, 100.0)] + [flat(i) for i in range(2, 30)]
    t = run(bars).trades[0]
    assert t.exit_reason == "time"
    assert t.sessions_held == 20
    assert t.exit_ms == bars[20].ts_ms  # entry day is session 1, so session 20 is bar index 20
    assert abs(t.exit_price - 100.0 * (1 - 0.0005)) < 0.02
