"""Feed ticks into 1s and 1m bar builders (V8-P2 / V6 shadow path)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import Bar
from data.bars import BarBuilder, BarBuilder1s, Tick


@dataclass
class MultiBarFeed:
    """Dual-resolution bar builder for live SnapQuote research."""

    builder_1s: BarBuilder1s = field(default_factory=BarBuilder1s)
    builder_1m: BarBuilder = field(default_factory=BarBuilder)
    closed_1s: list[Bar] = field(default_factory=list)
    closed_1m: list[Bar] = field(default_factory=list)
    ticks_seen: int = 0

    def on_tick(self, tick: Tick, now_ms: int | None = None) -> tuple[list[Bar], list[Bar]]:
        self.ticks_seen += 1
        c1 = self.builder_1s.on_tick(tick, now_ms=now_ms)
        c60 = self.builder_1m.on_tick(tick, now_ms=now_ms)
        self.closed_1s.extend(c1)
        self.closed_1m.extend(c60)
        return c1, c60

    def flush(self, symbol: str | None = None) -> tuple[list[Bar], list[Bar]]:
        f1 = self.builder_1s.flush(symbol)
        f60 = self.builder_1m.flush(symbol)
        self.closed_1s.extend(f1)
        self.closed_1m.extend(f60)
        return f1, f60
