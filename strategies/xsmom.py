"""S7 cross-sectional momentum (PLAN_V2 V3-2 / PREREG T5). Book B monthly rebalance."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")


class XSMom:
    id = "S7_xsmom"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        """Emit a long only on the first trading day of the month when ranked in top N.

        Ranking itself is portfolio-level (lab/portfolio + universe_on). Here we only
        fire when ctx.extras says this symbol is a pick for today.
        """
        closed = bars.closed()
        if len(closed) < 252:
            return []
        last = closed[-1]
        d = datetime.fromtimestamp(last.ts_ms / 1000, tz=IST).date()
        if d.day > 5:  # only early-month windows; exact "first trading day" is caller's job
            return []
        if not ctx.extras.get("xsmom_pick"):
            return []
        closes = [b.close for b in closed]
        ret6 = closes[-1] / closes[-126] - 1.0 if closes[-126] else 0.0
        ret12 = closes[-1] / closes[-252] - 1.0 if closes[-252] else 0.0
        daily = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
        vol = math.sqrt(sum(x * x for x in daily[-60:]) / max(1, len(daily[-60:]))) or 1e-6
        atr_proxy = abs(closes[-1] - closes[-20]) / 20.0
        stop = closes[-1] - 3.0 * max(atr_proxy, closes[-1] * 0.01)
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=closes[-1],
                stop=stop,
                target=None,
                time_exit_ms=None,
                features={"ret6": ret6, "ret12": ret12, "vol": vol, "score": (ret6 + ret12) / (2 * vol)},
                strategy=self.id,
                book="B",
            )
        ]
