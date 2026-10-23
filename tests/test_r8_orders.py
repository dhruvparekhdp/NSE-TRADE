"""R8 / V4-5: watchdog crossed_since_ms, tag lookup, square_off LIMIT exit."""

from __future__ import annotations

from broker.paper import PaperBroker
from core.orders import OrderManager


def test_watchdog_not_on_first_crossing_tick():
    b = PaperBroker(capital=500_000)
    om = OrderManager(b, stop_watchdog_s=10)
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
    b.on_tick("SBIN", 100.0, ask=100.0)
    om.on_fill({"client_tag": br.entry.client_tag, "qty": 100, "price": 100.0, "purpose": "entry"}, now_ms=1_100)
    assert br.stop is not None
    # First tick through stop — must NOT fire watchdog exit yet
    om.tick_watchdog("SBIN", 97.0, now_ms=2_000)
    assert not any(o.client_tag.endswith("W") for o in b.orders.values())
    # After 10s continuous crossing, watchdog places exit
    om.tick_watchdog("SBIN", 97.0, now_ms=12_500)
    assert any(o.client_tag.endswith("W") for o in b.orders.values())


def test_square_off_sends_protected_limit():
    b = PaperBroker(capital=500_000)
    om = OrderManager(b)
    br = om.submit_bracket(
        trade_id=1,
        trade_date="2026-10-23",
        strategy_code="OR",
        symbol="SBIN",
        side=1,
        qty=50,
        book="A",
        entry_ref=100,
        stop=98,
        target=104,
        ask=100,
        now_ms=1_000,
    )
    b.on_tick("SBIN", 100.0, ask=100.0)
    om.on_fill({"client_tag": br.entry.client_tag, "qty": 50, "price": 100.0, "purpose": "entry"}, now_ms=1_100)
    b.last_ltp["SBIN"] = 101.0
    om.square_off("SBIN")
    sq = b.get_order_by_tag(br.entry.client_tag + "Q")
    assert sq is not None
    assert sq.order_type == "LIMIT" and sq.purpose == "square_off"


def test_angel_get_order_by_tag_idempotent():
    from broker.angel import AngelBroker

    calls: list[str] = []

    class FakeApi:
        def placeOrder(self, params):  # noqa: N802
            calls.append(params["ordertag"])
            return {"status": True, "data": {"orderid": "1"}}

    ab = AngelBroker(api=FakeApi(), totp_now=lambda: "000000")
    # Bypass live guard for unit test
    ab._live_guard = lambda: None  # type: ignore[method-assign]
    kw = dict(
        client_tag="ne261023AOR0001",
        symbol="SBIN-EQ",
        side="BUY",
        qty=1,
        order_type="LIMIT",
        product="INTRADAY",
        purpose="entry",
        price=100.0,
        trigger=None,
    )
    ab.place_order(**kw)
    ab.place_order(**kw)
    assert len(calls) == 1
    assert ab.get_order_by_tag("ne261023AOR0001") is not None
