"""Sizing and entry gates — pure (plan A9.3 / P2-3; review R2)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.types import Book, Signal, SizeResult


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float = 1.0
    min_position_inr: float = 100_000.0
    min_position_cnc_inr: float = 20_000.0
    max_position_pct_capital: float = 300.0
    max_mis_exposure_x: float = 3.0
    max_open_intraday: int = 3
    max_open_swing: int = 4  # ₹25k slots at ₹1L so CNC floor clears (R2)
    max_open_per_sector: int = 2  # Book B: at most N open CNC names per NSE Industry (V-NEXT N4)
    daily_loss_limit_pct: float = 2.0
    floor_pct: float = 80.0
    max_spread_pct: float = 0.10
    circuit_buffer_pct: float = 2.0
    kill_switch: bool = False
    news_filter_enabled: bool = False
    news_block_threshold: float = -0.5  # block new entries when sentiment <= this
    surveillance_symbols: frozenset[str] = frozenset()


@dataclass
class PortfolioState:
    capital: float
    start_capital: float
    day_pnl_pct: float = 0.0
    open_intraday: int = 0
    open_swing: int = 0
    mis_exposure: float = 0.0
    open_symbols: set[str] | None = None
    open_sector_counts: dict[str, int] | None = None
    session_allows_entry: bool = True
    spread_pct: float | None = None
    dist_to_circuit_pct: float | None = None
    results_day: bool = False
    news_score: float | None = None

    def __post_init__(self) -> None:
        if self.open_symbols is None:
            self.open_symbols = set()
        if self.open_sector_counts is None:
            self.open_sector_counts = {}


def _floor_qty(raw: float) -> int:
    return max(0, int(raw))


def on_swing_open(state: PortfolioState, symbol: str, sector_map: dict[str, str] | None) -> None:
    if not sector_map:
        return
    from data.sectors import sector_for

    sec = sector_for(symbol, sector_map)
    counts = state.open_sector_counts or {}
    counts[sec] = counts.get(sec, 0) + 1
    state.open_sector_counts = counts


def on_swing_close(state: PortfolioState, symbol: str, sector_map: dict[str, str] | None) -> None:
    if not sector_map:
        return
    from data.sectors import sector_for

    sec = sector_for(symbol, sector_map)
    counts = state.open_sector_counts or {}
    n = counts.get(sec, 0)
    if n <= 1:
        counts.pop(sec, None)
    else:
        counts[sec] = n - 1
    state.open_sector_counts = counts


def book_b_slot_healthy(
    capital: float,
    max_open_swing: int,
    min_position_cnc_inr: float,
) -> bool:
    """False when equal slots cannot clear 1.1× the CNC floor (review R2)."""
    if max_open_swing <= 0 or capital <= 0 or min_position_cnc_inr <= 0:
        return False
    return (capital / max_open_swing) >= 1.1 * min_position_cnc_inr


def size(
    entry: float,
    stop: float,
    capital: float,
    risk_pct: float,
    tick: float,
    book: Book,
    limits: RiskLimits,
) -> SizeResult:
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or entry <= 0 or capital <= 0:
        return SizeResult(0, 0.0, "bad_prices")
    # Round stop distance up to tick so qty is conservative
    if tick > 0:
        steps = int(risk_per_share / tick + 0.999999)
        risk_per_share = max(tick, steps * tick)
    qty = _floor_qty((capital * risk_pct / 100.0) / risk_per_share)
    value = qty * entry
    if book == "A":
        if value < limits.min_position_inr and qty > 0:
            return SizeResult(0, 0.0, "below_min_position")
        cap_value = capital * limits.max_position_pct_capital / 100.0
        if value > cap_value and entry > 0:
            qty = _floor_qty(cap_value / entry)
            value = qty * entry
            if value < limits.min_position_inr:
                return SizeResult(0, 0.0, "below_min_position")
    else:
        # Equal slots; cap risk size to the slot, then meet CNC floor when the slot allows (R2).
        slot = capital / max(1, limits.max_open_swing)
        if value > slot and entry > 0:
            qty = _floor_qty(slot / entry)
            value = qty * entry
        if value < limits.min_position_cnc_inr:
            if slot + 1e-9 >= limits.min_position_cnc_inr and entry > 0:
                qty_min = int(math.ceil(limits.min_position_cnc_inr / entry - 1e-12))
                if qty_min * entry <= slot + 1e-9:
                    qty = qty_min
                    value = qty * entry
                else:
                    return SizeResult(0, 0.0, "below_min_cnc_position")
            else:
                return SizeResult(0, 0.0, "below_min_cnc_position")
    if qty <= 0:
        return SizeResult(0, 0.0, "qty_zero")
    return SizeResult(qty, value, "ok")


def can_open(
    state: PortfolioState,
    plan: Signal,
    limits: RiskLimits,
    now_ms: int,
    *,
    new_position_value: float = 0.0,
    sector_map: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Ordered checks from plan A9.3. Returns (ok, machine_reason)."""
    _ = now_ms
    if limits.kill_switch:
        return False, "kill_switch"
    if plan.symbol.upper() in limits.surveillance_symbols:
        return False, "surveillance"
    if state.capital < state.start_capital * limits.floor_pct / 100.0:
        return False, "floor"
    if plan.book == "A" and state.day_pnl_pct <= -limits.daily_loss_limit_pct:
        return False, "daily_loss_limit"
    if not state.session_allows_entry:
        return False, "session_closed"
    if plan.book == "A" and state.open_intraday >= limits.max_open_intraday:
        return False, "max_open_intraday"
    if plan.book == "B" and state.open_swing >= limits.max_open_swing:
        return False, "max_open_swing"
    if plan.book == "B" and limits.max_open_per_sector > 0 and sector_map is not None:
        from data.sectors import sector_for

        sec = sector_for(plan.symbol, sector_map)
        open_in_sec = (state.open_sector_counts or {}).get(sec, 0)
        if open_in_sec >= limits.max_open_per_sector:
            return False, "sector_cap"
    if plan.book == "A":
        # B26: include the new position's value in the exposure check
        projected = state.mis_exposure + max(0.0, new_position_value)
        if projected > state.capital * limits.max_mis_exposure_x:
            return False, "mis_exposure"
    if plan.symbol in (state.open_symbols or set()):
        return False, "symbol_open"
    if state.spread_pct is not None and state.spread_pct > limits.max_spread_pct:
        return False, "spread_wide"
    if state.dist_to_circuit_pct is not None and state.dist_to_circuit_pct < limits.circuit_buffer_pct:
        return False, "near_circuit"
    if state.results_day:
        return False, "results_day"
    if limits.news_filter_enabled and state.news_score is not None:
        if state.news_score <= limits.news_block_threshold and plan.side == 1:
            return False, "news_risk_off"
        if state.news_score >= -limits.news_block_threshold and plan.side == -1:
            if state.news_score >= abs(limits.news_block_threshold):
                return False, "news_risk_on_short_block"
    return True, "ok"


def limits_from_settings(settings: Any) -> RiskLimits:
    surv: frozenset[str] = frozenset()
    try:
        from data.surveillance import load_surveillance_symbols

        surv = load_surveillance_symbols()
    except Exception:  # noqa: BLE001
        surv = frozenset()
    return RiskLimits(
        risk_per_trade_pct=float(getattr(settings, "risk_per_trade_pct", 1.0)),
        min_position_inr=float(getattr(settings, "min_position_inr", 100_000.0)),
        min_position_cnc_inr=float(getattr(settings, "min_position_cnc_inr", 20_000.0)),
        max_position_pct_capital=float(getattr(settings, "max_position_pct_capital", 300.0)),
        max_mis_exposure_x=float(getattr(settings, "max_mis_exposure_x", 3.0)),
        max_open_intraday=int(getattr(settings, "max_open_intraday", 3)),
        max_open_swing=int(getattr(settings, "max_open_swing", 4)),
        max_open_per_sector=int(getattr(settings, "max_open_per_sector", 2)),
        daily_loss_limit_pct=float(getattr(settings, "daily_loss_limit_pct", 2.0)),
        floor_pct=float(getattr(settings, "floor_pct", 80.0)),
        max_spread_pct=float(getattr(settings, "max_spread_pct", 0.10)),
        circuit_buffer_pct=float(getattr(settings, "circuit_buffer_pct", 2.0)),
        kill_switch=bool(getattr(settings, "kill_switch", False)),
        news_filter_enabled=bool(getattr(settings, "news_filter_enabled", False)),
        news_block_threshold=float(getattr(settings, "news_block_threshold", -0.5)),
        surveillance_symbols=surv,
    )
