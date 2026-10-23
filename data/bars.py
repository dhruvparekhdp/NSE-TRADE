"""Ticks → 1m bars; late/out-of-order handling (plan P1-6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from core.types import Bar

IST = ZoneInfo("Asia/Kolkata")


def minute_floor_ms(ts_ms: int) -> int:
    """Exchange-time IST minute open as UTC epoch ms."""
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=IST)
    floored = dt.replace(second=0, microsecond=0)
    return int(floored.timestamp() * 1000)


@dataclass
class Tick:
    symbol: str
    ts_ms: int
    ltp: float
    volume_traded: int = 0
    bid: float | None = None
    ask: float | None = None


@dataclass
class BarBuilder:
    late_slack_ms: int = 5_000
    current: dict[str, Bar] = field(default_factory=dict)
    finished: list[Bar] = field(default_factory=list)
    spreads: dict[str, tuple[float, float, int, int]] = field(default_factory=dict)
    _last_vol: dict[str, int] = field(default_factory=dict)

    def on_tick(self, tick: Tick, now_ms: int | None = None) -> list[Bar]:
        """Build 1m bars. Late ticks within `late_slack_ms` still update that minute (V6-2)."""
        now = now_ms if now_ms is not None else tick.ts_ms
        key = tick.symbol
        minute = minute_floor_ms(tick.ts_ms)
        # Drop ticks that are too late to safely amend a finished minute
        if now - tick.ts_ms > self.late_slack_ms and minute < minute_floor_ms(now) - 60_000:
            return []
        closed: list[Bar] = []
        cur = self.current.get(key)
        # Out-of-order: tick belongs to an older minute we already finished — amend if in slack
        if cur is not None and minute < cur.ts_ms:
            for i, b in enumerate(self.finished):
                if b.ts_ms == minute and key:  # finished list is flat; amend matching open time
                    self.finished[i] = Bar(
                        ts_ms=b.ts_ms,
                        open=b.open,
                        high=max(b.high, tick.ltp),
                        low=min(b.low, tick.ltp),
                        close=tick.ltp,
                        volume=b.volume,
                        source="ws",
                    )
                    return []
            return []
        if cur is not None and cur.ts_ms != minute:
            closed.append(cur)
            self.finished.append(cur)
            del self.current[key]
            cur = None
        delta_vol = 0
        prev = self._last_vol.get(key)
        if prev is not None and tick.volume_traded >= prev:
            delta_vol = tick.volume_traded - prev
        self._last_vol[key] = tick.volume_traded
        if cur is None:
            self.current[key] = Bar(
                ts_ms=minute,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
                volume=delta_vol,
                source="ws",
            )
        else:
            self.current[key] = Bar(
                ts_ms=cur.ts_ms,
                open=cur.open,
                high=max(cur.high, tick.ltp),
                low=min(cur.low, tick.ltp),
                close=tick.ltp,
                volume=cur.volume + delta_vol,
                source="ws",
            )
        if tick.bid is not None and tick.ask is not None:
            self.spreads[key] = (tick.bid, tick.ask, 0, 0)
        return closed

    def flush(self, symbol: str | None = None) -> list[Bar]:
        out = []
        keys = [symbol] if symbol else list(self.current.keys())
        for k in keys:
            if k in self.current:
                out.append(self.current.pop(k))
                self.finished.append(out[-1])
        return out


def resample(bars: list[Bar], minutes: int) -> list[Bar]:
    if minutes <= 1 or not bars:
        return list(bars)
    out: list[Bar] = []
    bucket: list[Bar] = []
    bucket_start: int | None = None
    span = minutes * 60_000
    for b in bars:
        start = (b.ts_ms // span) * span
        if bucket_start is None:
            bucket_start = start
        if start != bucket_start:
            out.append(_agg(bucket_start, bucket))
            bucket = []
            bucket_start = start
        bucket.append(b)
    if bucket and bucket_start is not None:
        out.append(_agg(bucket_start, bucket))
    return out


def _agg(ts_ms: int, bars: list[Bar]) -> Bar:
    return Bar(
        ts_ms=ts_ms,
        open=bars[0].open,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        close=bars[-1].close,
        volume=sum(b.volume for b in bars),
        source=bars[0].source,
    )
