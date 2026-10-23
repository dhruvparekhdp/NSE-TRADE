"""Sizing and entry gates — pure (plan A9.3 / P2-3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.types import Book, Signal, SizeResult


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float = 1.0
    min_position_inr: float = 100_000.0
    max_position_pct_capital: float = 300.0
    max_mis_exposure_x: float = 3.0
    max_open_intraday: int = 3
    max_open_swing: int = 5
    daily_loss_limit_pct: float = 2.0
    floor_pct: float = 80.0
    max_spread_pct: float = 0.10
    circuit_buffer_pct: float = 2.0
    kill_switch: bool = False
    news_filter_enabled: bool = False
    news_block_threshold: float = -0.5  # block new entries when sentiment <= this


@dataclass
class PortfolioState:
    capital: float
    start_capital: float
    day_pnl_pct: float = 0.0
    open_intraday: int = 0
    open_swing: int = 0
    mis_exposure: float = 0.0
    open_symbols: set[str] | None = None
    session_allows_entry: bool = True
    spread_pct: float | None = None
    dist_to_circuit_pct: float | None = None
    results_day: bool = False
    news_score: float | None = None

    def __post_init__(self) -> None:
        if self.open_symbols is None:
            self.open_symbols = set()


def _floor_qty(raw: float) -> int:
    return max(0, int(raw))


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
        slot = capital / max(1, limits.max_open_swing)
        if value > slot and entry > 0:
            qty = _floor_qty(slot / entry)
            value = qty * entry
    if qty <= 0:
        return SizeResult(0, 0.0, "qty_zero")
    return SizeResult(qty, value, "ok")


def can_open(state: PortfolioState, plan: Signal, limits: RiskLimits, now_ms: int) -> tuple[bool, str]:
    """Ordered checks from plan A9.3. Returns (ok, machine_reason)."""
    _ = now_ms
    if limits.kill_switch:
        return False, "kill_switch"
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
    if plan.book == "A":
        # provisional: reject if already at exposure cap (caller passes current exposure)
        if state.mis_exposure >= state.capital * limits.max_mis_exposure_x:
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
            # strongly positive news: skip shorts
            if state.news_score >= abs(limits.news_block_threshold):
                return False, "news_risk_on_short_block"
    return True, "ok"


def limits_from_settings(settings: Any) -> RiskLimits:
    return RiskLimits(
        risk_per_trade_pct=float(getattr(settings, "risk_per_trade_pct", 1.0)),
        min_position_inr=float(getattr(settings, "min_position_inr", 100_000.0)),
        max_position_pct_capital=float(getattr(settings, "max_position_pct_capital", 300.0)),
        max_mis_exposure_x=float(getattr(settings, "max_mis_exposure_x", 3.0)),
        max_open_intraday=int(getattr(settings, "max_open_intraday", 3)),
        max_open_swing=int(getattr(settings, "max_open_swing", 5)),
        daily_loss_limit_pct=float(getattr(settings, "daily_loss_limit_pct", 2.0)),
        floor_pct=float(getattr(settings, "floor_pct", 80.0)),
        max_spread_pct=float(getattr(settings, "max_spread_pct", 0.10)),
        circuit_buffer_pct=float(getattr(settings, "circuit_buffer_pct", 2.0)),
        kill_switch=bool(getattr(settings, "kill_switch", False)),
        news_filter_enabled=bool(getattr(settings, "news_filter_enabled", False)),
        news_block_threshold=float(getattr(settings, "news_block_threshold", -0.5)),
    )
