"""Ticks → 1m bars; late/out-of-order handling (plan P1-6)."""

from __future__ import annotations

from collections.abc import Callable
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


def second_floor_ms(ts_ms: int) -> int:
    """Exchange-time IST second open as UTC epoch ms (V8-P2 research bars)."""
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=IST)
    floored = dt.replace(microsecond=0)
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
class BarBuilder1s:
    """SnapQuote ticks → 1-second OHLCV bars (research; not stored long-term by default)."""

    late_slack_ms: int = 1_500
    current: dict[str, Bar] = field(default_factory=dict)
    finished: list[Bar] = field(default_factory=list)
    _last_vol: dict[str, int] = field(default_factory=dict)

    def on_tick(self, tick: Tick, now_ms: int | None = None) -> list[Bar]:
        return _on_tick_bucket(
            tick,
            now_ms,
            bucket_ms=second_floor_ms(tick.ts_ms),
            bucket_fn=second_floor_ms,
            late_slack_ms=self.late_slack_ms,
            current=self.current,
            finished=self.finished,
            last_vol=self._last_vol,
        )

    def flush(self, symbol: str | None = None) -> list[Bar]:
        return _flush_bars(self.current, self.finished, symbol)


@dataclass
class BarBuilder:
    late_slack_ms: int = 5_000
    current: dict[str, Bar] = field(default_factory=dict)
    finished: list[Bar] = field(default_factory=list)
    spreads: dict[str, tuple[float, float, int, int]] = field(default_factory=dict)
    _last_vol: dict[str, int] = field(default_factory=dict)

    def on_tick(self, tick: Tick, now_ms: int | None = None) -> list[Bar]:
        """Build 1m bars. Late ticks within `late_slack_ms` still update that minute (V6-2)."""
        closed = _on_tick_bucket(
            tick,
            now_ms,
            bucket_ms=minute_floor_ms(tick.ts_ms),
            bucket_fn=minute_floor_ms,
            late_slack_ms=self.late_slack_ms,
            current=self.current,
            finished=self.finished,
            last_vol=self._last_vol,
            bucket_span_ms=60_000,
        )
        if tick.bid is not None and tick.ask is not None:
            self.spreads[tick.symbol] = (tick.bid, tick.ask, 0, 0)
        return closed

    def flush(self, symbol: str | None = None) -> list[Bar]:
        return _flush_bars(self.current, self.finished, symbol)


def _flush_bars(
    current: dict[str, Bar],
    finished: list[Bar],
    symbol: str | None,
) -> list[Bar]:
    out: list[Bar] = []
    keys = [symbol] if symbol else list(current.keys())
    for k in keys:
        if k in current:
            out.append(current.pop(k))
            finished.append(out[-1])
    return out


def _on_tick_bucket(
    tick: Tick,
    now_ms: int | None,
    *,
    bucket_ms: int,
    bucket_fn: Callable[[int], int],
    late_slack_ms: int,
    current: dict[str, Bar],
    finished: list[Bar],
    last_vol: dict[str, int],
    bucket_span_ms: int = 1_000,
) -> list[Bar]:
    now = now_ms if now_ms is not None else tick.ts_ms
    key = tick.symbol
    if now - tick.ts_ms > late_slack_ms and bucket_ms < bucket_fn(now) - bucket_span_ms:
        return []
    closed: list[Bar] = []
    cur = current.get(key)
    if cur is not None and bucket_ms < cur.ts_ms:
        for i, b in enumerate(finished):
            if b.ts_ms == bucket_ms:
                finished[i] = Bar(
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
    if cur is not None and cur.ts_ms != bucket_ms:
        closed.append(cur)
        finished.append(cur)
        del current[key]
        cur = None
    delta_vol = 0
    prev = last_vol.get(key)
    if prev is not None and tick.volume_traded >= prev:
        delta_vol = tick.volume_traded - prev
    last_vol[key] = tick.volume_traded
    if cur is None:
        current[key] = Bar(
            ts_ms=bucket_ms,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=delta_vol,
            source="ws",
        )
    else:
        current[key] = Bar(
            ts_ms=cur.ts_ms,
            open=cur.open,
            high=max(cur.high, tick.ltp),
            low=min(cur.low, tick.ltp),
            close=tick.ltp,
            volume=cur.volume + delta_vol,
            source="ws",
        )
    return closed


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
