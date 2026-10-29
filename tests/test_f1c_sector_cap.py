"""F1c: sector cap skip reason on scan."""

from __future__ import annotations

from core.risk import PortfolioState, RiskLimits, can_open, on_swing_open
from core.types import Signal


def _sig(sym: str) -> Signal:
    return Signal(
        ts_ms=1,
        symbol=sym,
        side=1,
        entry_ref=100.0,
        stop=95.0,
        target=None,
        time_exit_ms=None,
        features={},
        strategy="S6_swing",
        book="B",
        role="pick",
    )


def test_sector_cap_reason():
    sm = {"TCS": "IT SERVICES", "INFY": "IT SERVICES", "WIPRO": "IT SERVICES"}
    st = PortfolioState(capital=100_000, start_capital=100_000, open_swing=2)
    on_swing_open(st, "TCS", sm)
    on_swing_open(st, "INFY", sm)
    ok, reason = can_open(st, _sig("WIPRO"), RiskLimits(max_open_per_sector=2), 0, sector_map=sm)
    assert not ok and reason == "sector_cap"
