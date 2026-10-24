"""S6 / S6b daily swing breakouts (plan A10) — Book B, enough for evening backtests."""

from __future__ import annotations

from core.indicators import atr, donchian_high, ema, keltner, sma
from core.types import Bar, Signal
from strategies.base import BarView, Context


class SwingDonchian:
    id = "S6_swing"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 55:
            return []
        for b in closed:
            bars.require_no_future(b)
        closes = [b.close for b in closed]
        highs = [b.high for b in closed]
        lows = [b.low for b in closed]
        # Donchian 20 of *prior* highs (exclude today): use highs[:-1]
        prior_highs = highs[:-1]
        if len(prior_highs) < 20:
            return []
        don = max(prior_highs[-20:])
        sma50 = sma(closes, 50)
        if sma50[-1] is None or sma50[-2] is None:
            return []
        rising = sma50[-1] > sma50[-2]
        last = closed[-1]
        if not (last.close > don and rising):
            return []
        a = atr(highs, lows, closes, 14)[-1]
        if a is None:
            return []
        entry = last.close * 1.005  # next-day limit at prev close +0.5%
        stop = entry - 2.5 * a
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=entry,
                stop=stop,
                target=None,
                time_exit_ms=None,
                features={"donchian20": don, "atr14": a, "news_score": ctx.news_score},
                strategy=self.id,
                book="B",
            )
        ]


class SwingDonchianOpen:
    """S6 with next-day open entry (PREREG T6) instead of close×1.005 limit."""

    id = "S6_swing_open"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        base = SwingDonchian()
        sigs = base.on_bar(symbol, bars, ctx)
        out: list[Signal] = []
        for s in sigs:
            atr = float((s.features or {}).get("atr14") or 0)
            out.append(
                Signal(
                    ts_ms=s.ts_ms,
                    symbol=s.symbol,
                    side=s.side,
                    entry_ref=bars.closed()[-1].close,
                    stop=bars.closed()[-1].close - 2.5 * atr if atr else s.stop,
                    target=s.target,
                    time_exit_ms=s.time_exit_ms,
                    features={**(s.features or {}), "entry_mode": "open"},
                    strategy=self.id,
                    book="B",
                )
            )
        return out


class SwingKeltner:
    id = "S6b_keltner"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]:
        closed = bars.closed()
        if len(closed) < 40:
            return []
        closes = [b.close for b in closed]
        highs = [b.high for b in closed]
        lows = [b.low for b in closed]
        _mid, upper, _lower = keltner(closes, highs, lows, 20, 2.0)
        last = closed[-1]
        if upper[-1] is None or last.close <= upper[-1]:
            return []
        a = atr(highs, lows, closes, 14)[-1]
        if a is None:
            return []
        entry = last.close * 1.005
        stop = entry - 2.5 * a
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=entry,
                stop=stop,
                target=None,
                time_exit_ms=None,
                features={"keltner_upper": upper[-1], "atr14": a, "news_score": ctx.news_score},
                strategy=self.id,
                book="B",
            )
        ]


def bars_from_daily_df(rows: list[dict]) -> list[Bar]:
    """Helper: date YYYYMMDD int or str -> Bar at 09:15 IST ≈ that day's open ts."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    out: list[Bar] = []
    for r in rows:
        d = str(int(r["date"]))
        dt = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]), 9, 15, tzinfo=ist)
        out.append(
            Bar(
                ts_ms=int(dt.timestamp() * 1000),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=int(r.get("volume") or 0),
                source=str(r.get("source") or "bhav"),
            )
        )
    return out


# silence unused import lint if donchian_high unused — used conceptually
_ = (donchian_high, ema)
