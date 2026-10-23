"""Event-driven backtester using shared exits / risk / costs (plan A11 / PLAN_V2 V2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.costs import cost_in_r, rates_for, round_trip
from core.exits import ExitRules, Position, fill_entry, step_exits
from core.indicators import atr as atr_series
from core.risk import PortfolioState, RiskLimits, can_open, size
from core.sessions import daily_bar_close_ms
from core.types import Bar, Signal
from data.universe import universe_on
from lab.context import bars_for_strategy
from strategies.base import BarView, Context, Strategy, mirror, random_baseline


def symbols_tradable_on(d: date, candidates: list[str] | None = None) -> list[str]:
    """Filter candidates by survivorship history (PLAN_V2 V1-6)."""
    allowed = universe_on(d)
    if candidates is None:
        return sorted(allowed)
    return [s for s in candidates if s.upper() in allowed]


@dataclass
class BTTrade:
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
    gross_inr: float = 0.0
    costs_inr: float = 0.0
    net_inr: float = 0.0
    r_mult: float = 0.0
    role: str = "pick"
    sessions_held: int = 0


@dataclass
class BacktestResult:
    trades: list[BTTrade] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    no_fills: list[Signal] = field(default_factory=list)


def _fill_path(bar: Bar, side: int) -> list[float]:
    if side > 0:
        return [bar.open, bar.low, bar.high, bar.close]
    return [bar.open, bar.high, bar.low, bar.close]


def _close_bt(tr: BTTrade, px: float, ts_ms: int, reason: str, sessions: int) -> None:
    tr.exit_ms = ts_ms
    tr.exit_price = px
    tr.exit_reason = reason
    tr.sessions_held = sessions
    signed = tr.side
    tr.gross_inr = (px - tr.entry_price) * tr.qty * signed
    buy_v = tr.entry_price * tr.qty if signed > 0 else px * tr.qty
    sell_v = px * tr.qty if signed > 0 else tr.entry_price * tr.qty
    product = "CNC" if tr.book == "B" else "MIS"
    tr.costs_inr = round_trip(buy_v, sell_v, product, rates_for(product)).total  # type: ignore[arg-type]
    slip = (buy_v + sell_v) * (0.05 if tr.book == "B" else 0.03) / 100.0
    tr.costs_inr = round(tr.costs_inr + slip, 2)
    tr.net_inr = tr.gross_inr - tr.costs_inr
    risk = abs(tr.entry_price - tr.stop_init) * tr.qty
    tr.r_mult = tr.net_inr / risk if risk else 0.0


def run_daily_book(
    *,
    symbol: str,
    daily_bars: list[Bar],
    strategy: Strategy,
    capital: float = 100_000.0,
    limits: RiskLimits | None = None,
    ctx_factory: Any = None,
    hold_sessions: int = 20,
) -> BacktestResult:
    """Book B daily backtest with correct LIMIT fills, gap stops, trail (V2-1)."""
    limits = limits or RiskLimits()
    state = PortfolioState(capital=capital, start_capital=capital)
    result = BacktestResult()
    rules = ExitRules(
        product="CNC",
        slippage_pct=0.05,
        stop_extra_slip_pct=0.05,
        trail_atr_mult=2.5,
        max_sessions=hold_sessions,
        entry_limit_offset_pct=0.0,
    )
    open_pos: Position | None = None
    open_trade: BTTrade | None = None
    pending: Signal | None = None

    for i in range(len(daily_bars)):
        bar = daily_bars[i]
        # After close for signals; entry uses the bar's own open as fill day 09:15
        decision_ms = daily_bar_close_ms(bar.ts_ms) + 1_000  # after CAS / session close (R12)
        view = BarView(bars=daily_bars[: i + 1], decision_ms=decision_ms, timeframe="1d")
        ctx = Context(trade_date=str(i), news_score=None)
        if ctx_factory:
            ctx = ctx_factory(i, daily_bars, view)

        # Try fill pending entry on this bar (next day after signal)
        if pending is not None and open_pos is None:
            fill = fill_entry(pending, bar, rules)
            if fill is None:
                result.no_fills.append(pending)
                pending = None
            else:
                sz = size(
                    fill.price,
                    pending.stop,
                    state.capital,
                    limits.risk_per_trade_pct,
                    0.05,
                    pending.book,
                    limits,
                )
                if sz.qty <= 0:
                    # R2: size refusal is not a market no_fill — keep the machine reason.
                    pending.features = {
                        **(pending.features or {}),
                        "skip_reason": sz.reason,
                    }
                    pending = None
                else:
                    risk_inr = abs(fill.price - pending.stop) * sz.qty
                    open_pos = Position(
                        symbol=symbol,
                        strategy=pending.strategy,
                        book=pending.book,
                        side=pending.side,
                        qty=sz.qty,
                        entry_ms=fill.ts_ms,
                        entry_price=fill.price,
                        stop_init=pending.stop,
                        stop=pending.stop,
                        risk_inr=risk_inr,
                        target=pending.target,
                        sessions_held=0,
                    )
                    open_trade = BTTrade(
                        symbol=symbol,
                        strategy=pending.strategy,
                        book=pending.book,
                        side=pending.side,
                        qty=sz.qty,
                        entry_ms=fill.ts_ms,
                        entry_price=fill.price,
                        stop_init=pending.stop,
                        role="pick",
                    )
                    state.open_swing += 1
                    state.open_symbols.add(symbol)
                    atr_from_sig = pending.features.get("atr14") if pending else None
                    pending = None
                    # Entry day: stop applies from the open (conservative) — step this bar
                    atr_f = float(atr_from_sig) if atr_from_sig else None
                    open_pos, ev = step_exits(open_pos, bar, rules, atr=atr_f)
                    if ev:
                        _close_bt(open_trade, ev.price, ev.ts_ms, ev.reason, open_pos.sessions_held)
                        result.trades.append(open_trade)
                        state.open_swing = max(0, state.open_swing - 1)
                        state.open_symbols.discard(symbol)
                        open_pos = None
                        open_trade = None
                    continue

        # Manage open position on subsequent bars
        if open_pos is not None and open_trade is not None:
            # R13 / PLAN A10: trail from current ATR14 on daily bars, not entry stop/2.5
            hs = [b.high for b in daily_bars[: i + 1]]
            ls = [b.low for b in daily_bars[: i + 1]]
            cs = [b.close for b in daily_bars[: i + 1]]
            atr14 = atr_series(hs, ls, cs, 14)[-1]
            atr_f = float(atr14) if atr14 is not None else None
            open_pos, ev = step_exits(open_pos, bar, rules, atr=atr_f)
            if ev:
                _close_bt(open_trade, ev.price, ev.ts_ms, ev.reason, open_pos.sessions_held)
                result.trades.append(open_trade)
                state.open_swing = max(0, state.open_swing - 1)
                state.open_symbols.discard(symbol)
                open_pos = None
                open_trade = None
            continue

        if open_pos is not None or pending is not None:
            continue

        sigs = strategy.on_bar(symbol, view, ctx)
        for sig in sigs:
            result.signals.append(sig)
            result.signals.append(mirror(sig))
            if i > 0:
                result.signals.append(random_baseline(sig, daily_bars[i - 1].ts_ms, daily_bars[i].ts_ms))
            ok, _reason = can_open(state, sig, limits, decision_ms)
            if not ok or sig.role != "pick":
                continue
            pending = sig
            break

    if open_trade is not None and open_pos is not None:
        last = daily_bars[-1]
        px = last.close * (1 - 0.0005)
        _close_bt(open_trade, px, last.ts_ms, "eod", open_pos.sessions_held)
        result.trades.append(open_trade)
    return result


def run_intraday_day(
    *,
    symbol: str,
    bars_1m: list[Bar],
    strategies: list[Strategy],
    capital: float = 100_000.0,
    limits: RiskLimits | None = None,
    ctx: Context | None = None,
    square_off_ms: int | None = None,
) -> BacktestResult:
    """Single-day Book A replay on 1m bars with both-side stops / targets (V2-2)."""
    limits = limits or RiskLimits(min_position_inr=100_000.0)
    state = PortfolioState(capital=capital, start_capital=capital, session_allows_entry=True)
    result = BacktestResult()
    rules = ExitRules(
        product="MIS",
        slippage_pct=0.03,
        stop_extra_slip_pct=0.05,
        trail_atr_mult=0.0,
        max_sessions=10_000,
        square_off_ms=square_off_ms,
    )
    open_pos: Position | None = None
    open_tr: BTTrade | None = None
    ctx = ctx or Context(trade_date="day")
    # R5: one trade per strategy × symbol × day (no re-entry after a stop).
    done_today: set[str] = set()

    for i, bar in enumerate(bars_1m):
        decision_ms = bar.ts_ms + 60_000

        if open_pos is not None and open_tr is not None:
            open_pos, ev = step_exits(open_pos, bar, rules, atr=None)
            if ev:
                _close_bt(open_tr, ev.price, ev.ts_ms, ev.reason, open_pos.sessions_held)
                result.trades.append(open_tr)
                done_today.add(open_tr.strategy)
                state.open_intraday = 0
                state.open_symbols.discard(symbol)
                open_pos = None
                open_tr = None
            continue

        for strat in strategies:
            if strat.book != "A":
                continue
            if strat.id in done_today:
                continue
            # R6 / B14: resample 1m → strategy timeframe before on_bar
            tf_bars = bars_for_strategy(bars_1m[: i + 1], strat.timeframe)
            view = BarView(bars=tf_bars, decision_ms=decision_ms, timeframe=strat.timeframe)
            for sig in strat.on_bar(symbol, view, ctx):
                result.signals.append(sig)
                ok, _ = can_open(state, sig, limits, decision_ms)
                if not ok:
                    continue
                sz = size(sig.entry_ref, sig.stop, state.capital, limits.risk_per_trade_pct, 0.05, "A", limits)
                if sz.qty <= 0:
                    continue
                open_pos = Position(
                    symbol=symbol,
                    strategy=sig.strategy,
                    book="A",
                    side=sig.side,
                    qty=sz.qty,
                    entry_ms=decision_ms,
                    entry_price=sig.entry_ref,
                    stop_init=sig.stop,
                    stop=sig.stop,
                    risk_inr=abs(sig.entry_ref - sig.stop) * sz.qty,
                    target=sig.target,
                )
                open_tr = BTTrade(
                    symbol=symbol,
                    strategy=sig.strategy,
                    book="A",
                    side=sig.side,
                    qty=sz.qty,
                    entry_ms=decision_ms,
                    entry_price=sig.entry_ref,
                    stop_init=sig.stop,
                )
                state.open_intraday = 1
                state.open_symbols.add(symbol)
                done_today.add(sig.strategy)
                break
            if open_tr:
                break

    if open_tr is not None and open_pos is not None:
        last = bars_1m[-1]
        _close_bt(open_tr, last.close, last.ts_ms, "square_off", open_pos.sessions_held)
        result.trades.append(open_tr)
    return result


__all__ = [
    "BacktestResult",
    "BTTrade",
    "run_daily_book",
    "run_intraday_day",
    "cost_in_r",
    "symbols_tradable_on",
]
