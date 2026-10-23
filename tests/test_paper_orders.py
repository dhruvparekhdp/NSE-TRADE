"""Paper broker fills + order manager OCO/timeout (P2-4/5)."""

from __future__ import annotations

from broker.paper import PaperBroker
from core.orders import OrderManager


def test_limit_buy_fill_and_tag_idempotent():
    b = PaperBroker(capital=200_000)
    o1 = b.place_order(
        client_tag="ne261023AOR0001",
        symbol="SBIN",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        product="INTRADAY",
        purpose="entry",
        price=100.0,
        trigger=None,
    )
    o2 = b.place_order(
        client_tag="ne261023AOR0001",
        symbol="SBIN",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        product="INTRADAY",
        purpose="entry",
        price=100.0,
        trigger=None,
    )
    assert o1 is o2
    fills = b.on_tick("SBIN", 99.0, ask=99.0, bid=98.5)
    assert fills and fills[0]["price"] >= 99.0


def test_stop_gap_through_stays_open():
    b = PaperBroker(capital=200_000)
    b.place_order(
        client_tag="t1",
        symbol="SBIN",
        side="SELL",
        qty=10,
        order_type="STOPLOSS_LIMIT",
        product="INTRADAY",
        purpose="stop",
        price=95.0,
        trigger=100.0,
    )
    # gap way below limit
    fills = b.on_tick("SBIN", 90.0)
    assert fills == []
    assert b.orders["t1"].status == "OPEN"


def test_bracket_timeout_and_oco():
    b = PaperBroker(capital=500_000)
    om = OrderManager(b, entry_timeout_s=1)
    br = om.submit_bracket(
        trade_id=1,
        trade_date="2026-10-23",
        strategy_code="OR",
        symbol="SBIN",
        side=1,
        qty=100,
        book="A",
        entry_ref=100,
        stop=98,
        target=104,
        ask=100,
        now_ms=1_000,
    )
    om.cancel_unfilled_entries(now_ms=3_000)
    assert br.entry.status == "CANCELLED"

    br2 = om.submit_bracket(
        trade_id=2,
        trade_date="2026-10-23",
        strategy_code="OR",
        symbol="SBIN",
        side=1,
        qty=100,
        book="A",
        entry_ref=100,
        stop=98,
        target=104,
        ask=100,
        now_ms=5_000,
    )
    fills = b.on_tick("SBIN", 100.0, ask=100.0)
    for f in fills:
        om.on_fill(f, now_ms=5_100)
    assert br2.stop is not None and br2.target is not None
    # target fill cancels stop
    b.on_tick("SBIN", 104.0, bid=104.0)
    # manually notify target fill
    tgt = br2.target
    om.on_fill(
        {"client_tag": tgt.client_tag, "qty": 100, "price": 104.0, "purpose": "target"},
        now_ms=6_000,
    )
    assert br2.stop.status == "CANCELLED"
