"""N4: max two open Book B names per NSE Industry."""

from __future__ import annotations

from core.risk import PortfolioState, RiskLimits, can_open, on_swing_close, on_swing_open
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
    )


def test_sector_cap_blocks_third_same_industry():
    sector_map = {
        "TCS": "IT SERVICES",
        "INFY": "IT SERVICES",
        "WIPRO": "IT SERVICES",
    }
    st = PortfolioState(capital=100_000, start_capital=100_000, open_swing=2)
    on_swing_open(st, "TCS", sector_map)
    on_swing_open(st, "INFY", sector_map)
    ok, reason = can_open(st, _sig("WIPRO"), RiskLimits(max_open_per_sector=2), 0, sector_map=sector_map)
    assert not ok and reason == "sector_cap"


def test_sector_cap_allows_different_industry():
    sector_map = {"TCS": "IT SERVICES", "RELIANCE": "OIL & GAS"}
    st = PortfolioState(capital=100_000, start_capital=100_000, open_swing=1)
    on_swing_open(st, "TCS", sector_map)
    ok, reason = can_open(st, _sig("RELIANCE"), RiskLimits(max_open_per_sector=2), 0, sector_map=sector_map)
    assert ok and reason == "ok"


def test_on_swing_close_frees_slot():
    sector_map = {"TCS": "IT SERVICES", "INFY": "IT SERVICES"}
    st = PortfolioState(capital=100_000, start_capital=100_000, open_swing=2)
    on_swing_open(st, "TCS", sector_map)
    on_swing_open(st, "INFY", sector_map)
    on_swing_close(st, "TCS", sector_map)
    st.open_swing = 1
    sm = {**sector_map, "WIPRO": "IT SERVICES"}
    ok, _ = can_open(st, _sig("WIPRO"), RiskLimits(max_open_per_sector=2), 0, sector_map=sm)
    assert ok
