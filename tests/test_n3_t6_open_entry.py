"""T6: next-day open entry vs limit."""

from __future__ import annotations

from core.exits import ExitRules, fill_entry, fill_entry_at_open
from core.types import Bar, Signal


def test_open_entry_fills_when_limit_would_not():
    bar = Bar(ts_ms=1_000, open=101.0, high=105.0, low=100.0, close=104.0, volume=1)
    sig = Signal(
        ts_ms=0,
        symbol="X",
        side=1,
        entry_ref=99.0,
        stop=95.0,
        target=None,
        time_exit_ms=None,
        features={},
        strategy="S6_swing",
        book="B",
    )
    assert fill_entry(sig, bar, ExitRules(entry_limit_offset_pct=0.0)) is None
    assert fill_entry_at_open(sig, bar, ExitRules(slippage_pct=0.0)).price == 101.0
