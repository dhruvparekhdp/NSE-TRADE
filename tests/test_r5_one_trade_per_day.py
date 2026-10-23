"""R5: after a stop, the same strategy must not re-enter that symbol the same day."""

from __future__ import annotations

from core.types import Bar, Signal
from lab.backtest import run_intraday_day
from strategies.base import Context


class _AlwaysGap:
    id = "S2_gap"
    book = "A"
    timeframe = "1m"

    def on_bar(self, symbol: str, bars, ctx: Context) -> list[Signal]:  # noqa: ANN001
        closed = bars.closed()
        if len(closed) < 2:
            return []
        last = closed[-1]
        # Wide stop so first bar after entry can stop out, then signal keeps firing
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=last.close,
                stop=last.close * 0.999,
                target=None,
                time_exit_ms=None,
                strategy=self.id,
                book="A",
                role="pick",
            )
        ]


def test_no_reentry_after_stop_same_day():
    # 200 one-minute bars: price dips immediately after each hypothetical entry
    bars: list[Bar] = []
    base = 1_700_000_000_000
    px = 100.0
    for i in range(200):
        o = px
        # alternate: green then red so a long stop at 0.999*entry can hit
        c = px * (0.998 if i % 2 else 1.001)
        bars.append(
            Bar(
                ts_ms=base + i * 60_000,
                open=o,
                high=max(o, c) * 1.001,
                low=min(o, c) * 0.997,
                close=c,
                volume=100,
            )
        )
        px = c
    # Book A size needs large capital / low min for the probe
    from core.risk import RiskLimits

    lim = RiskLimits(min_position_inr=1_000.0, risk_per_trade_pct=1.0, max_open_intraday=3)
    bt = run_intraday_day(
        symbol="X",
        bars_1m=bars,
        strategies=[_AlwaysGap()],
        capital=500_000.0,
        limits=lim,
    )
    n = sum(1 for t in bt.trades if t.strategy == "S2_gap")
    assert n <= 1, f"expected at most one S2_gap trade, got {n}"
