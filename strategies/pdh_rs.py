"""S5 previous-day-high + relative strength (plan A10)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.indicators import session_vwap
from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")

class PDHRS:
    id = "S5_pdh_rs"
    book = "A"
    timeframe = "5m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        pdh = float(ctx.extras.get("pdh") or 0)
        rs_rank = float(ctx.extras.get("rs_rank") or 99)
        if pdh <= 0 or len(closed) < 20:
            return []
        last = closed[-1]
        hm = _hm(last.ts_ms)
        if not (9*60+45 <= hm <= 13*60+30):
            return []
        if last.close <= pdh:
            return []
        if rs_rank > 10:
            return []
        highs=[b.high for b in closed]
        lows=[b.low for b in closed]
        closes=[b.close for b in closed]
        vols=[b.volume for b in closed]
        vwap = session_vwap(highs,lows,closes,vols)[-1]
        if vwap is None:
            return []
        if abs(last.close - vwap)/last.close*100 > 1.5:
            return []
        stop = vwap
        r = last.close - stop
        if r <= 0:
            return []
        target = last.close + 2*r
        return [Signal(ts_ms=last.ts_ms,symbol=symbol,side=1,entry_ref=last.close,stop=stop,target=target,
                       time_exit_ms=_exit(last.ts_ms),
                       features={"pdh":pdh,"rs_rank":rs_rank,"vwap":vwap,"news_score":ctx.news_score},
                       strategy=self.id,book="A")]

def _hm(ts_ms: int) -> int:
    t = datetime.fromtimestamp(ts_ms/1000, tz=IST).timetz().replace(tzinfo=None)
    return t.hour*60+t.minute

def _exit(ts_ms: int) -> int:
    d = datetime.fromtimestamp(ts_ms/1000,tz=IST).date()
    return int(datetime(d.year,d.month,d.day,15,5,tzinfo=IST).timestamp()*1000)
