"""Strategy protocol, BarView (no lookahead), mirror + random baseline (plan A10)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.sessions import daily_bar_close_ms
from core.types import Bar, Book, Signal


class LookaheadError(Exception):
    """Raised when a strategy asks for a bar that has not closed yet."""


def _timeframe_ms(timeframe: str) -> int:
    """Bar length in ms. Daily close is per-bar via sessions.json (R12)."""
    tf = (timeframe or "1m").lower()
    if tf in {"1d", "d", "day", "daily"}:
        return 0  # unused for daily; see daily_bar_close_ms
    if tf.endswith("m"):
        return int(tf[:-1] or "1") * 60_000
    if tf.endswith("h"):
        return int(tf[:-1] or "1") * 3_600_000
    return 60_000


@dataclass
class BarView:
    """Only exposes bars that have closed by decision_ms (PLAN_V2 V2-3 / R12)."""

    bars: list[Bar]
    decision_ms: int
    timeframe: str = "1m"
    asset_class: str = "fo"

    def closed(self) -> list[Bar]:
        width = _timeframe_ms(self.timeframe)
        daily = self.timeframe.lower() in {"1d", "d", "day", "daily"}
        out: list[Bar] = []
        for b in self.bars:
            close_ms = (
                daily_bar_close_ms(b.ts_ms, self.asset_class)
                if daily
                else b.ts_ms + width
            )
            if close_ms > self.decision_ms:
                continue  # forming bar — exclude, do not crash live callers (R12)
            out.append(b)
        return out

    def at(self, index: int) -> Bar:
        closed = self.closed()
        if index < 0:
            index = len(closed) + index
        if index < 0 or index >= len(closed):
            raise IndexError(index)
        return closed[index]

    def require_no_future(self, bar: Bar) -> None:
        if bar.ts_ms + 60_000 > self.decision_ms:
            raise LookaheadError(f"future bar {bar.ts_ms} at decision {self.decision_ms}")


@dataclass
class Context:
    trade_date: str
    nifty_ret_open: float = 0.0
    india_vix: float | None = None
    news_score: float | None = None
    results_due: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    id: str
    book: Book
    timeframe: str

    def on_bar(self, symbol: str, bars: BarView, ctx: Context) -> list[Signal]: ...


def mirror(sig: Signal) -> Signal:
    stop_dist = abs(sig.entry_ref - sig.stop)
    side = -1 if sig.side > 0 else 1
    stop = sig.entry_ref + stop_dist if side < 0 else sig.entry_ref - stop_dist
    target = None
    if sig.target is not None:
        r = abs(sig.target - sig.entry_ref)
        target = sig.entry_ref - r if side < 0 else sig.entry_ref + r
    return Signal(
        ts_ms=sig.ts_ms,
        symbol=sig.symbol,
        side=side,  # type: ignore[arg-type]
        entry_ref=sig.entry_ref,
        stop=stop,
        target=target,
        time_exit_ms=sig.time_exit_ms,
        features=dict(sig.features),
        strategy=sig.strategy,
        book=sig.book,
        role="mirror",
    )


def random_baseline(sig: Signal, window_start_ms: int, window_end_ms: int) -> Signal:
    """Deterministic random entry minute in window (plan A10)."""
    h = hashlib.sha256(f"{sig.strategy}:{sig.symbol}:{sig.ts_ms}".encode()).hexdigest()
    span = max(60_000, window_end_ms - window_start_ms)
    offset = (int(h[:8], 16) % (span // 60_000)) * 60_000
    return Signal(
        ts_ms=window_start_ms + offset,
        symbol=sig.symbol,
        side=sig.side,
        entry_ref=sig.entry_ref,
        stop=sig.stop,
        target=sig.target,
        time_exit_ms=sig.time_exit_ms,
        features=dict(sig.features),
        strategy=sig.strategy,
        book=sig.book,
        role="random",
    )
