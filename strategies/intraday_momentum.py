"""S4 afternoon momentum (plan A10)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.indicators import atr, session_vwap
from core.types import Signal
from strategies.base import BarView, Context

IST = ZoneInfo("Asia/Kolkata")

class AfternoonMomo:
    id = "S4_momo"
    book = "A"
    timeframe = "5m"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 50:
            return []
        last = closed[-1]
        t = datetime.fromtimestamp(last.ts_ms/1000, tz=IST)
        if not (t.hour == 14 and t.minute == 0):
            # fire only on 14:00 bar close
            if not (t.hour == 14 and t.minute <= 1):
                return []
        morning = [b for b in closed if 9*60+15 <= _hm(b.ts_ms) <= 10*60+15]
        if len(morning) < 5:
            return []
        ret = (morning[-1].close - morning[0].open)/morning[0].open*100
        decile = float(ctx.extras.get("ret_decile") or 5)
        highs=[b.high for b in closed]
        lows=[b.low for b in closed]
        closes=[b.close for b in closed]
        vols=[b.volume for b in closed]
        vwap = session_vwap(highs,lows,closes,vols)[-1]
        if vwap is None:
            return []
        a = atr(highs,lows,closes,14)[-1]
        if a is None:
            return []
        sigs = []
        if decile >= 9 and last.close > vwap:
            stop = last.close - a
            sigs.append(Signal(ts_ms=last.ts_ms,symbol=symbol,side=1,entry_ref=last.close,stop=stop,target=None,
                               time_exit_ms=_exit(last.ts_ms),features={"ret":ret,"vwap":vwap,"news_score":ctx.news_score},
                               strategy=self.id,book="A"))
        if decile <= 1 and last.close < vwap:
            stop = last.close + a
            sigs.append(Signal(ts_ms=last.ts_ms,symbol=symbol,side=-1,entry_ref=last.close,stop=stop,target=None,
                               time_exit_ms=_exit(last.ts_ms),features={"ret":ret,"vwap":vwap,"news_score":ctx.news_score},
                               strategy=self.id,book="A"))
        return sigs

def _hm(ts_ms: int) -> int:
    t = datetime.fromtimestamp(ts_ms/1000, tz=IST).timetz().replace(tzinfo=None)
    return t.hour*60+t.minute

def _exit(ts_ms: int) -> int:
    d = datetime.fromtimestamp(ts_ms/1000,tz=IST).date()
    return int(datetime(d.year,d.month,d.day,15,5,tzinfo=IST).timestamp()*1000)
