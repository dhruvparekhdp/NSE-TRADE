"""P2-1: A2.1 cost vectors to the paisa."""

from __future__ import annotations

from core.costs import cost_in_r, order_brokerage, rates_for, round_trip


def test_intraday_round_trip_vectors():
    rates = rates_for("MIS")
    # ₹1,00,000 round trip from plan table ≈ ₹82.5 before slippage
    bd = round_trip(100_000, 100_000, "MIS", rates)
    assert abs(bd.total - 82.45) < 1.0  # allow paisa rounding drift across sources
    assert bd.brokerage == 40.0  # 20+20
    assert abs(bd.stt - 25.0) < 0.01


def test_delivery_example_approx():
    rates = rates_for("CNC")
    bd = round_trip(50_000, 50_000, "CNC", rates)
    # plan ≈ ₹181.9 for 50k RT
    assert 170 <= bd.total <= 200


def test_brokerage_min_flat_vs_pct():
    rates = rates_for("MIS")
    assert order_brokerage(1_000, rates) == 1.0  # 0.1% of 1000
    assert order_brokerage(100_000, rates) == 20.0


def test_cost_in_r_positive():
    r = cost_in_r(100_000, 1.0, "MIS", rates_for("MIS"), slippage_pct=0.03)
    assert r > 0
