"""S1 Opening Range Breakout (plan A10)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")

class ORB:
    id = "S1_orb"
    book = "A"
    timeframe = "5m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 5:
            return []
        # build 5m from 1m by grouping
        by_min = closed
        or_bars = []
        signal_bars = []
        for b in by_min:
            t = datetime.fromtimestamp(b.ts_ms/1000, tz=IST).timetz().replace(tzinfo=None)
            hm = t.hour*60+t.minute
            if 9*60+15 <= hm < 9*60+30:
                or_bars.append(b)
            elif 9*60+30 <= hm <= 11*60+30:
                signal_bars.append(b)
        if len(or_bars) < 1 or not signal_bars:
            return []
        or_high = max(b.high for b in or_bars)
        or_low = min(b.low for b in or_bars)
        mid = (or_high+or_low)/2 or 1
        width_pct = (or_high-or_low)/mid*100
        if width_pct < 0.4 or width_pct > 2.5:
            return []
        gap = float(ctx.extras.get("gap_pct") or 0)
        if abs(gap) > 3:
            return []
        # use last closed bar as 5m proxy: require close above OR high
        last = signal_bars[-1]
        if last.close <= or_high:
            return []
        # volume filter: last vol > 1.5x avg of prior same-slot if provided
        slot_avg = ctx.extras.get("slot_vol_avg")
        if slot_avg and last.volume < 1.5 * float(slot_avg):
            return []
        stop = or_low
        r = last.close - stop
        if r <= 0:
            return []
        target = last.close + 2*r
        # square off ~15:05
        d = datetime.fromtimestamp(last.ts_ms/1000, tz=IST).date()
        exit_dt = datetime(d.year,d.month,d.day,15,5,tzinfo=IST)
        return [Signal(ts_ms=last.ts_ms, symbol=symbol, side=1, entry_ref=last.close, stop=stop,
                       target=target, time_exit_ms=int(exit_dt.timestamp()*1000),
                       features={"or_high":or_high,"or_low":or_low,"width_pct":width_pct,"news_score":ctx.news_score},
                       strategy=self.id, book="A")]
