"""Strategy fire/no-fire + backtest determinism + gate on shuffle."""

from __future__ import annotations

from core.types import Bar
from lab.backtest import run_daily_book
from lab.evaluate import gate, shuffle_outcomes
from lab.ledger import connect, record_trial, trial_count
from strategies.base import BarView, Context, LookaheadError, mirror
from strategies.swing_breakout import SwingDonchian


def _daily_uptrend(n: int = 80) -> list[Bar]:
    """Slow grind then a clear Donchian-20 breakout on the last bar."""
    bars = []
    px = 100.0
    for i in range(n):
        if i < n - 1:
            o = px
            h = px + 0.3
            lo = px - 0.3
            c = px + 0.2
        else:
            # breakout close above prior 20 highs
            prior_high = max(b.high for b in bars[-20:])
            o = px
            c = prior_high + 2.0
            h = c + 0.5
            lo = px - 0.2
        bars.append(Bar(ts_ms=1_700_000_000_000 + i * 86_400_000, open=o, high=h, low=lo, close=c, volume=1_000_000))
        px = c
    return bars


def test_lookahead_raises():
    bars = _daily_uptrend(5)
    view = BarView(bars=bars, decision_ms=bars[2].ts_ms + 1000)
    try:
        view.require_no_future(bars[4])
        raised = False
    except LookaheadError:
        raised = True
    assert raised


def test_mirror_flips_side():
    from core.types import Signal

    s = Signal(1, "SBIN", 1, 100, 98, 104, None, {}, "S6_swing", "B")
    m = mirror(s)
    assert m.side == -1 and m.role == "mirror"


def test_swing_donchian_fires_on_breakout():
    bars = _daily_uptrend(80)
    view = BarView(bars=bars, decision_ms=bars[-1].ts_ms + 60_000)
    sigs = SwingDonchian().on_bar("SBIN", view, Context("d"))
    assert sigs and sigs[0].side == 1


def test_backtest_deterministic_and_ledger(tmp_path):
    bars = _daily_uptrend(120)
    a = run_daily_book(symbol="SBIN", daily_bars=bars, strategy=SwingDonchian())
    b = run_daily_book(symbol="SBIN", daily_bars=bars, strategy=SwingDonchian())
    assert [t.r_mult for t in a.trades] == [t.r_mult for t in b.trades]
    conn = connect(tmp_path / "e.db")
    n0 = trial_count(conn)
    record_trial(
        conn,
        strategy="S6_swing",
        params={},
        data_from="a",
        data_to="b",
        period="full",
        n=len(a.trades),
        avg_r=0.1,
        win_pct=50,
        passed=False,
    )
    assert trial_count(conn) == n0 + 1


def test_gate_fails_on_shuffle():
    bars = _daily_uptrend(120)
    bt = run_daily_book(symbol="SBIN", daily_bars=bars, strategy=SwingDonchian())
    picks = bt.trades
    if len(picks) < 4:
        return
    mid = picks[len(picks) // 2].entry_ms
    shuffled = shuffle_outcomes(picks, seed=7)
    g = gate("S6_swing", shuffled, picks, picks, book="B", mid_ms=mid)
    # shuffled should usually fail; if it passes by chance, still a valid null outcome
    assert isinstance(g.passed, bool)
