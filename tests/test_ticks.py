"""V0-4: tick rounding (PLAN_V2 B9)."""

from __future__ import annotations

from broker.paper import PaperBroker
from core.orders import OrderManager
from core.ticks import round_to_tick, tick_for_price


def test_round_to_tick_up_down_on_010():
    assert round_to_tick(1234.56, 0.10, "up") == 1234.60
    assert round_to_tick(1234.56, 0.10, "down") == 1234.50


def test_band_fallback_below_250_uses_001():
    assert tick_for_price(249.99) == 0.01
    assert round_to_tick(249.994, 0.01, "nearest") == 249.99


def test_order_manager_emits_on_tick_prices():
    b = PaperBroker(capital=200_000)
    om = OrderManager(b)
    # ₹0.10 band (1000–5000): raw limit would be 1235.06175… off-tick
    br = om.submit_bracket(
        trade_id=1,
        trade_date="2026-01-02",
        strategy_code="S1",
        symbol="SBIN",
        side=1,
        qty=1,
        book="A",
        entry_ref=1234.56,
        stop=1216.11,
        target=1250.0,
        ask=1234.56,
        now_ms=1,
        tick=0.10,
    )
    assert abs(br.entry.price * 10 - round(br.entry.price * 10)) < 1e-9
    assert br.entry.price == round_to_tick(br.entry.price, 0.10, "nearest")
    assert br.stop_trigger == round_to_tick(1216.11, 0.10, "up")
    assert br.stop_limit == round_to_tick(br.stop_limit, 0.10, "nearest")
