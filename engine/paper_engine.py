"""Book B paper cycle jobs (PLAN_V2 V4-6 / review R1). Shared exits with lab/backtest."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.costs import rates_for, round_trip
from core.exits import ExitRules, Position, fill_entry, step_exits, virtual_outcome
from core.risk import PortfolioState, RiskLimits, can_open, size
from core.types import Bar, Signal
from strategies.base import BarView, Context, Strategy, mirror, random_baseline

log = logging.getLogger(__name__)


def eod_fill_pending(
    pending: list[Signal],
    bars: dict[str, Bar],
    rules: ExitRules | None = None,
) -> list[dict[str, Any]]:
    """Apply today's daily bar to pending LIMIT entries (job_eod_fill)."""
    rules = rules or ExitRules(product="CNC", entry_limit_offset_pct=0.0)
    out: list[dict[str, Any]] = []
    for sig in pending:
        bar = bars.get(sig.symbol)
        if bar is None:
            out.append({"signal": sig, "status": "no_bar"})
            continue
        fill = fill_entry(sig, bar, rules)
        out.append({"signal": sig, "status": "filled" if fill else "no_fill", "fill": fill})
    return out


def resolve_outcomes(
    signals: list[Signal],
    bars_by_symbol: dict[str, list[Bar]],
    rules: ExitRules | None = None,
) -> list[dict[str, Any]]:
    """virtual_outcome for take/skip/mirror/random (job_outcomes)."""
    rules = rules or ExitRules(product="CNC")
    rows: list[dict[str, Any]] = []
    for sig in signals:
        bars = bars_by_symbol.get(sig.symbol) or []
        rows.append({"signal_id": getattr(sig, "id", None), "role": sig.role, **virtual_outcome(sig, bars, rules)})
    return rows


def scan_book_b_day(
    *,
    symbol: str,
    daily_bars: list[Bar],
    strategy: Strategy,
    state: PortfolioState,
    limits: RiskLimits,
    decision_ms: int,
    ctx: Context | None = None,
) -> list[Signal]:
    """job_scan: signals on today's closed daily bar (pick + mirror + random)."""
    view = BarView(bars=daily_bars, decision_ms=decision_ms, timeframe="1d")
    ctx = ctx or Context(trade_date="scan")
    out: list[Signal] = []
    for sig in strategy.on_bar(symbol, view, ctx):
        out.append(sig)
        out.append(mirror(sig))
        if len(daily_bars) >= 2:
            out.append(random_baseline(sig, daily_bars[-2].ts_ms, daily_bars[-1].ts_ms))
    return out


@dataclass
class PaperTrade:
    symbol: str
    strategy: str
    book: str
    side: int
    qty: int
    entry_ms: int
    entry_price: float
    stop_init: float
    exit_ms: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    net_inr: float = 0.0
    r_mult: float = 0.0


@dataclass
class PaperReplayResult:
    trades: list[PaperTrade] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


def _close_paper(tr: PaperTrade, px: float, ts_ms: int, reason: str) -> None:
    tr.exit_ms = ts_ms
    tr.exit_price = px
    tr.exit_reason = reason
    signed = tr.side
    gross = (px - tr.entry_price) * tr.qty * signed
    buy_v = tr.entry_price * tr.qty if signed > 0 else px * tr.qty
    sell_v = px * tr.qty if signed > 0 else tr.entry_price * tr.qty
    costs = round_trip(buy_v, sell_v, "CNC", rates_for("CNC")).total
    slip = (buy_v + sell_v) * 0.05 / 100.0
    tr.net_inr = gross - costs - slip
    risk = abs(tr.entry_price - tr.stop_init) * tr.qty
    tr.r_mult = tr.net_inr / risk if risk else 0.0


def replay_through_jobs(
    *,
    symbol: str,
    daily_bars: list[Bar],
    strategy: Strategy,
    capital: float = 100_000.0,
    limits: RiskLimits | None = None,
    hold_sessions: int = 20,
) -> PaperReplayResult:
    """Day-by-day job_scan → next-day job_eod_fill / step_exits — parity with lab/backtest.

    WHY (V4-6 / R1): the running engine must walk the same path as the lab, not a stub.
    """
    limits = limits or RiskLimits()
    state = PortfolioState(capital=capital, start_capital=capital)
    result = PaperReplayResult()
    rules = ExitRules(
        product="CNC",
        slippage_pct=0.05,
        stop_extra_slip_pct=0.05,
        trail_atr_mult=2.5,
        max_sessions=hold_sessions,
        entry_limit_offset_pct=0.0,
    )
    pending: Signal | None = None
    open_pos: Position | None = None
    open_tr: PaperTrade | None = None

    for i, bar in enumerate(daily_bars):
        decision_ms = bar.ts_ms + 6 * 3600 * 1000
        bars_so_far = daily_bars[: i + 1]

        # --- job_eod_fill: try to fill yesterday's pending on today's bar ---
        if pending is not None and open_pos is None:
            fills = eod_fill_pending([pending], {symbol: bar}, rules)
            fr = fills[0]
            if fr["status"] != "filled":
                pending.features = {**(pending.features or {}), "skip_reason": fr["status"]}
                pending = None
            else:
                fill = fr["fill"]
                sz = size(
                    fill.price,
                    pending.stop,
                    state.capital,
                    limits.risk_per_trade_pct,
                    0.05,
                    "B",
                    limits,
                )
                if sz.qty <= 0:
                    pending.features = {**(pending.features or {}), "skip_reason": sz.reason}
                    pending = None
                else:
                    open_pos = Position(
                        symbol=symbol,
                        strategy=pending.strategy,
                        book="B",
                        side=pending.side,
                        qty=sz.qty,
                        entry_ms=fill.ts_ms,
                        entry_price=fill.price,
                        stop_init=pending.stop,
                        stop=pending.stop,
                        risk_inr=abs(fill.price - pending.stop) * sz.qty,
                        target=pending.target,
                        sessions_held=0,
                    )
                    open_tr = PaperTrade(
                        symbol=symbol,
                        strategy=pending.strategy,
                        book="B",
                        side=pending.side,
                        qty=sz.qty,
                        entry_ms=fill.ts_ms,
                        entry_price=fill.price,
                        stop_init=pending.stop,
                    )
                    state.open_swing += 1
                    state.open_symbols.add(symbol)
                    atr_f = float((pending.features or {}).get("atr14") or 0) or None
                    pending = None
                    open_pos, ev = step_exits(open_pos, bar, rules, atr=atr_f)
                    if ev and open_tr:
                        _close_paper(open_tr, ev.price, ev.ts_ms, ev.reason)
                        result.trades.append(open_tr)
                        state.open_swing = max(0, state.open_swing - 1)
                        state.open_symbols.discard(symbol)
                        open_pos = None
                        open_tr = None
                    continue

        # --- manage open (same as backtest trail/stop/time) ---
        if open_pos is not None and open_tr is not None:
            atr_f = abs(open_tr.entry_price - open_tr.stop_init) / 2.5 or None
            open_pos, ev = step_exits(open_pos, bar, rules, atr=atr_f)
            if ev:
                _close_paper(open_tr, ev.price, ev.ts_ms, ev.reason)
                result.trades.append(open_tr)
                state.open_swing = max(0, state.open_swing - 1)
                state.open_symbols.discard(symbol)
                open_pos = None
                open_tr = None
            continue

        if open_pos is not None or pending is not None:
            continue

        # --- job_scan ---
        sigs = scan_book_b_day(
            symbol=symbol,
            daily_bars=bars_so_far,
            strategy=strategy,
            state=state,
            limits=limits,
            decision_ms=decision_ms,
        )
        result.signals.extend(sigs)
        for sig in sigs:
            ok, _ = can_open(state, sig, limits, decision_ms)
            if not ok or sig.role != "pick":
                continue
            pending = sig
            break

    if open_tr is not None and open_pos is not None:
        last = daily_bars[-1]
        _close_paper(open_tr, last.close * (1 - 0.0005), last.ts_ms, "eod")
        result.trades.append(open_tr)
    return result
