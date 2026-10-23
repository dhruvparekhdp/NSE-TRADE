"""S3 gap-fade and S3b gap-and-go (plan A10)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")

class GapFade:
    id = "S3_gapfade"
    book = "A"
    timeframe = "15m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 20:
            return []
        prev_close = float(ctx.extras.get("prev_close") or 0)
        if prev_close <= 0:
            return []
        first = [b for b in closed if _hm(b.ts_ms) >= 9*60+15][:15]  # ~first 15m of 1m bars
        if len(first) < 10:
            return []
        o, c = first[0].open, first[-1].close
        gap = (o - prev_close)/prev_close*100
        if gap < 1.5:
            return []
        if not (c < o):  # fade: first 15m closes below open
            return []
        entry = c
        stop = max(b.high for b in first)
        d = datetime.fromtimestamp(first[-1].ts_ms/1000,tz=IST).date()
        exit_dt = datetime(d.year,d.month,d.day,15,5,tzinfo=IST)
        return [Signal(ts_ms=first[-1].ts_ms,symbol=symbol,side=-1,entry_ref=entry,stop=stop,
                       target=prev_close,time_exit_ms=int(exit_dt.timestamp()*1000),
                       features={"gap_pct":gap,"news_score":ctx.news_score},strategy=self.id,book="A")]

class GapAndGo:
    id = "S3b_gapgo"
    book = "A"
    timeframe = "15m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        prev_close = float(ctx.extras.get("prev_close") or 0)
        if prev_close <= 0 or len(closed) < 20:
            return []
        first = [b for b in closed if _hm(b.ts_ms) >= 9*60+15][:15]
        if len(first) < 10:
            return []
        o, c = first[0].open, first[-1].close
        gap = (o - prev_close)/prev_close*100
        if abs(gap) < 1.5:
            return []
        # trade with gap direction
        with_gap = (gap > 0 and c > o) or (gap < 0 and c < o)
        if not with_gap:
            return []
        side = 1 if gap > 0 else -1
        entry = c
        extreme = min(b.low for b in first) if side>0 else max(b.high for b in first)
        stop = extreme
        r = abs(entry-stop)
        target = entry + (2*r if side>0 else -2*r)
        d = datetime.fromtimestamp(first[-1].ts_ms/1000,tz=IST).date()
        exit_dt = datetime(d.year,d.month,d.day,15,5,tzinfo=IST)
        return [Signal(ts_ms=first[-1].ts_ms,symbol=symbol,side=side,entry_ref=entry,stop=stop,target=target,
                       time_exit_ms=int(exit_dt.timestamp()*1000),
                       features={"gap_pct":gap,"news_score":ctx.news_score},strategy=self.id,book="A")]

def _hm(ts_ms: int) -> int:
    t = datetime.fromtimestamp(ts_ms/1000, tz=IST).timetz().replace(tzinfo=None)
    return t.hour*60+t.minute
