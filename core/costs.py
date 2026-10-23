"""Angel One cost model — pure functions (plan A2.1 / A9.2 / P2-1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Product = Literal["MIS", "CNC"]


@dataclass(frozen=True)
class CostRates:
    brokerage_flat_inr: float
    brokerage_pct: float
    stt_buy_pct: float
    stt_sell_pct: float
    exchange_pct: float
    sebi_pct: float
    stamp_buy_pct: float
    gst_pct: float
    dp_inr: float = 0.0
    dp_gst_pct: float = 18.0
    brokerage_min_inr: float = 5.0


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange: float
    sebi: float
    stamp: float
    gst: float
    dp: float
    total: float


def _r2(x: float) -> float:
    return round(x + 1e-12, 2)


def load_rates(path: Path | None = None) -> dict[str, Any]:
    p = path or Path(__file__).resolve().parent.parent / "config" / "costs_angel.json"
    return json.loads(p.read_text(encoding="utf-8"))


def rates_for(product: Product, raw: dict[str, Any] | None = None) -> CostRates:
    raw = raw or load_rates()
    key = "mis" if product == "MIS" else "cnc"
    d = raw[key]
    return CostRates(
        brokerage_flat_inr=float(d["brokerage_flat_inr"]),
        brokerage_pct=float(d["brokerage_pct"]),
        stt_buy_pct=float(d["stt_buy_pct"]),
        stt_sell_pct=float(d["stt_sell_pct"]),
        exchange_pct=float(d["exchange_pct"]),
        sebi_pct=float(d["sebi_pct"]),
        stamp_buy_pct=float(d["stamp_buy_pct"]),
        gst_pct=float(d["gst_pct"]),
        dp_inr=float(d.get("dp_inr", 0.0)),
        dp_gst_pct=float(d.get("dp_gst_pct", 18.0)),
        brokerage_min_inr=float(d.get("brokerage_min_inr", raw.get("brokerage_min_inr", 5.0))),
    )


def order_brokerage(value: float, rates: CostRates) -> float:
    """max(min ₹5, min(₹20, 0.1% of value)) per executed order (PLAN_V2 V1-4)."""
    capped = min(rates.brokerage_flat_inr, value * rates.brokerage_pct / 100.0)
    return _r2(max(rates.brokerage_min_inr, capped))


def round_trip(
    buy_value: float,
    sell_value: float,
    product: Product,
    rates: CostRates | None = None,
) -> CostBreakdown:
    rates = rates or rates_for(product)
    brok = order_brokerage(buy_value, rates) + order_brokerage(sell_value, rates)
    stt = _r2(buy_value * rates.stt_buy_pct / 100.0 + sell_value * rates.stt_sell_pct / 100.0)
    exchange = _r2((buy_value + sell_value) * rates.exchange_pct / 100.0)
    sebi = _r2((buy_value + sell_value) * rates.sebi_pct / 100.0)
    stamp = _r2(buy_value * rates.stamp_buy_pct / 100.0)
    gst = _r2((brok + exchange + sebi) * rates.gst_pct / 100.0)
    dp = 0.0
    if product == "CNC" and rates.dp_inr:
        dp = _r2(rates.dp_inr * (1.0 + rates.dp_gst_pct / 100.0))
    total = _r2(brok + stt + exchange + sebi + stamp + gst + dp)
    return CostBreakdown(brok, stt, exchange, sebi, stamp, gst, dp, total)


def cost_in_r(
    position_value: float,
    stop_pct: float,
    product: Product,
    rates: CostRates | None = None,
    slippage_pct: float = 0.0,
) -> float:
    """Round-trip cost + slippage as a multiple of risk (1R = stop_pct of position)."""
    bd = round_trip(position_value, position_value, product, rates)
    slip = position_value * (2.0 * slippage_pct / 100.0)
    risk = position_value * (stop_pct / 100.0)
    if risk <= 0:
        return float("inf")
    return (bd.total + slip) / risk
