"""S2 VWAP mean-reversion (plan A10)."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from core.indicators import rsi, session_vwap
from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")

class VWAPRevert:
    id = "S2_vwap"
    book = "A"
    timeframe = "5m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 30:
            return []
        last = closed[-1]
        t = datetime.fromtimestamp(last.ts_ms/1000, tz=IST)
        if t.hour*60+t.minute < 10*60+30:
            return []
        highs=[b.high for b in closed]
        lows=[b.low for b in closed]
        closes=[b.close for b in closed]
        vols=[b.volume for b in closed]
        vwap = session_vwap(highs,lows,closes,vols)
        if vwap[-1] is None:
            return []
        diffs = [c-v for c,v in zip(closes,vwap, strict=False) if v is not None]
        if len(diffs) < 10:
            return []
        mean = sum(diffs)/len(diffs)
        var = sum((d-mean)**2 for d in diffs)/len(diffs)
        std = math.sqrt(var) or 1e-9
        r = rsi(closes,14)[-1]
        if r is None:
            return []
        if not (closes[-1] < vwap[-1] - 2*std and r < 25):
            return []
        entry = closes[-1]
        stop = entry - std
        d = t.date()
        exit_dt = datetime(d.year,d.month,d.day,15,5,tzinfo=IST)
        return [Signal(ts_ms=last.ts_ms,symbol=symbol,side=1,entry_ref=entry,stop=stop,target=vwap[-1],
                       time_exit_ms=int(exit_dt.timestamp()*1000),
                       features={"vwap":vwap[-1],"std":std,"rsi":r,"news_score":ctx.news_score},
                       strategy=self.id,book="A")]
