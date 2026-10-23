"""Shared dataclasses for signals, bars, plans (plan A9 / A10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Book = Literal["A", "B"]
Side = Literal[1, -1]
Decision = Literal["taken", "skipped", "shadow"]


@dataclass(frozen=True)
class Bar:
    ts_ms: int  # bar open, UTC epoch ms
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "hist"


@dataclass
class Signal:
    ts_ms: int
    symbol: str
    side: Side
    entry_ref: float
    stop: float
    target: float | None
    time_exit_ms: int | None
    features: dict[str, Any] = field(default_factory=dict)
    strategy: str = ""
    book: Book = "A"
    role: Literal["pick", "mirror", "random"] = "pick"


@dataclass(frozen=True)
class TradePlan:
    signal: Signal
    qty: int
    value: float
    reason: str = ""


@dataclass(frozen=True)
class SizeResult:
    qty: int
    value: float
    reason: str
