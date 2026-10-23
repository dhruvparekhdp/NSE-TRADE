"""S7 cross-sectional momentum (PLAN_V2 V3-2 / PREREG T5; review R10). Book B monthly."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Signal
from strategies.base import BarView, Context
from strategies.xsmom_rank import atr20_stop

IST = ZoneInfo("Asia/Kolkata")


class XSMom:
    id = "S7_xsmom"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        """Entry when portfolio rank marks xsmom_pick; exit when xsmom_exit or ATR20 breached."""
        closed = bars.closed()
        if len(closed) < 252:
            return []
        last = closed[-1]
        closes = [b.close for b in closed]
        highs = [b.high for b in closed]
        lows = [b.low for b in closed]
        stop = atr20_stop(highs, lows, closes)
        if stop is None:
            return []

        if ctx.extras.get("xsmom_exit"):
            return [
                Signal(
                    ts_ms=last.ts_ms,
                    symbol=symbol,
                    side=-1,
                    entry_ref=closes[-1],
                    stop=closes[-1] * 1.01,
                    target=None,
                    time_exit_ms=None,
                    features={"exit_reason": "rebalance_out_of_top_2n"},
                    strategy=self.id,
                    book="B",
                    role="pick",
                )
            ]

        d = datetime.fromtimestamp(last.ts_ms / 1000, tz=IST).date()
        if d.day > 5:
            return []
        if not ctx.extras.get("xsmom_pick"):
            return []
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=closes[-1],
                stop=stop,
                target=None,
                time_exit_ms=None,
                features={"atr20": (closes[-1] - stop) / 3.0},
                strategy=self.id,
                book="B",
                role="pick",
            )
        ]
