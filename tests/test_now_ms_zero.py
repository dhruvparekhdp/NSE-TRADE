"""V0-3 / B25: now_ms=0 must not fall through to wall clock."""

from __future__ import annotations

from broker.paper import PaperBroker
from core.orders import OrderManager


def test_submit_bracket_accepts_now_ms_zero():
    b = PaperBroker(capital=200_000)
    om = OrderManager(b)
    br = om.submit_bracket(
        trade_id=1,
        trade_date="2026-01-02",
        strategy_code="S1",
        symbol="SBIN",
        side=1,
        qty=1,
        book="A",
        entry_ref=100.0,
        stop=99.0,
        target=102.0,
        now_ms=0,
    )
    assert br.entry.placed_ms == 0
