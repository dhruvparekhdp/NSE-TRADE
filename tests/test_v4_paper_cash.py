"""V4-3 / B7: PaperBroker cash must reflect P&L and costs."""

from __future__ import annotations

from broker.paper import PaperBroker


def test_mis_close_credits_pnl_minus_costs():
    br = PaperBroker(capital=100_000.0, mis_margin_pct=20.0, slippage_pct_mis=0.0)
    br.place_order(
        client_tag="e1",
        symbol="SBIN",
        side="BUY",
        qty=100,
        order_type="LIMIT",
        product="INTRADAY",
        purpose="entry",
        price=100.0,
    )
    br.on_tick("SBIN", 100.0, bid=100.0, ask=100.0)
    # +₹10k mark: sell at 200
    br.place_order(
        client_tag="x1",
        symbol="SBIN",
        side="SELL",
        qty=100,
        order_type="LIMIT",
        product="INTRADAY",
        purpose="exit",
        price=200.0,
    )
    br.on_tick("SBIN", 200.0, bid=200.0, ask=200.0)
    # equity ≈ 1,10,000 − costs (not stuck at 1,00,000)
    assert br.cash > 109_000.0
    assert br.cash < 110_500.0


def test_cnc_short_rejected():
    br = PaperBroker(capital=100_000.0)
    o = br.place_order(
        client_tag="s1",
        symbol="SBIN",
        side="SELL",
        qty=10,
        order_type="LIMIT",
        product="DELIVERY",
        purpose="entry",
        price=100.0,
    )
    fills = br.on_tick("SBIN", 100.0, bid=100.0, ask=100.0)
    assert fills == [] or o.status == "REJECTED" or "SBIN:DELIVERY" not in br.positions
