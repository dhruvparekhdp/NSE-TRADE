"""Event-driven backtester using the same strategy/risk/cost/paper objects (plan A11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from broker.paper import PaperBroker
from core.costs import cost_in_r, rates_for, round_trip
from core.risk import PortfolioState, RiskLimits, can_open, size
from core.types import Bar, Signal
from strategies.base import BarView, Context, Strategy, mirror, random_baseline


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


@dataclass
class BacktestResult:
    trades: list[BTTrade] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


def _fill_path(bar: Bar, side: int) -> list[float]:
    """Plan A11: open, then worse of high/low first for the position, then close."""
    if side > 0:
        # long: worse first = low then high
        return [bar.open, bar.low, bar.high, bar.close]
    return [bar.open, bar.high, bar.low, bar.close]


def run_daily_book(
    *,
    symbol: str,
    daily_bars: list[Bar],
    strategy: Strategy,
    capital: float = 50_000.0,
    limits: RiskLimits | None = None,
    ctx_factory: Any = None,
    hold_sessions: int = 20,
) -> BacktestResult:
    """Book B daily backtest — enough for evening research without 1m Angel data."""
    limits = limits or RiskLimits()
    broker = PaperBroker(capital=capital)
    state = PortfolioState(capital=capital, start_capital=capital)
    result = BacktestResult()
    open_trade: BTTrade | None = None
    held = 0

    for i in range(len(daily_bars)):
        decision_ms = daily_bars[i].ts_ms + 60_000  # after bar close
        view = BarView(bars=daily_bars[: i + 1], decision_ms=decision_ms)
        ctx = Context(trade_date=str(i), news_score=None)
        if ctx_factory:
            ctx = ctx_factory(i, daily_bars, view)

        # manage open trade
        if open_trade is not None:
            held += 1
            bar = daily_bars[i]
            stop = open_trade.stop_init
            # trail: highest close - 2.5 ATR approximated by raising stop only via features later; use fixed stop for v1
            hit_stop = bar.low <= stop
            if hit_stop:
                _close_trade(open_trade, stop, bar.ts_ms, "stop", broker)
                result.trades.append(open_trade)
                state.open_swing = max(0, state.open_swing - 1)
                state.open_symbols.discard(symbol)
                open_trade = None
                held = 0
            elif held >= hold_sessions:
                _close_trade(open_trade, bar.close, bar.ts_ms, "time", broker)
                result.trades.append(open_trade)
                state.open_swing = max(0, state.open_swing - 1)
                state.open_symbols.discard(symbol)
                open_trade = None
                held = 0

        if open_trade is not None:
            continue

        sigs = strategy.on_bar(symbol, view, ctx)
        for sig in sigs:
            result.signals.append(sig)
            result.signals.append(mirror(sig))
            # random baseline window = prior day
            if i > 0:
                result.signals.append(
                    random_baseline(sig, daily_bars[i - 1].ts_ms, daily_bars[i].ts_ms)
                )
            ok, reason = can_open(state, sig, limits, decision_ms)
            if not ok or sig.role != "pick":
                continue
            sz = size(sig.entry_ref, sig.stop, state.capital, limits.risk_per_trade_pct, 0.05, sig.book, limits)
            if sz.qty <= 0:
                continue
            # next-day open fill approximation at entry_ref
            entry_px = sig.entry_ref
            open_trade = BTTrade(
                symbol=symbol,
                strategy=sig.strategy,
                book=sig.book,
                side=sig.side,
                qty=sz.qty,
                entry_ms=decision_ms,
                entry_price=entry_px,
                stop_init=sig.stop,
                role="pick",
            )
            state.open_swing += 1
            state.open_symbols.add(symbol)
            held = 0
            break

    if open_trade is not None:
        last = daily_bars[-1]
        _close_trade(open_trade, last.close, last.ts_ms, "eod", broker)
        result.trades.append(open_trade)
    return result


def _close_trade(tr: BTTrade, px: float, ts_ms: int, reason: str, broker: PaperBroker) -> None:
    tr.exit_ms = ts_ms
    tr.exit_price = px
    tr.exit_reason = reason
    signed = tr.side
    tr.gross_inr = (px - tr.entry_price) * tr.qty * signed
    buy_v = tr.entry_price * tr.qty if signed > 0 else px * tr.qty
    sell_v = px * tr.qty if signed > 0 else tr.entry_price * tr.qty
    product = "CNC" if tr.book == "B" else "MIS"
    tr.costs_inr = round_trip(buy_v, sell_v, product, rates_for(product)).total  # type: ignore[arg-type]
    # add slippage estimate
    slip = (buy_v + sell_v) * (0.05 if tr.book == "B" else 0.03) / 100.0
    tr.costs_inr = round(tr.costs_inr + slip, 2)
    tr.net_inr = tr.gross_inr - tr.costs_inr
    risk = abs(tr.entry_price - tr.stop_init) * tr.qty
    tr.r_mult = tr.net_inr / risk if risk else 0.0


def run_intraday_day(
    *,
    symbol: str,
    bars_1m: list[Bar],
    strategies: list[Strategy],
    capital: float = 100_000.0,
    limits: RiskLimits | None = None,
    ctx: Context | None = None,
) -> BacktestResult:
    """Single-day Book A replay on 1m bars."""
    limits = limits or RiskLimits(min_position_inr=100_000.0)
    broker = PaperBroker(capital=capital)
    state = PortfolioState(capital=capital, start_capital=capital, session_allows_entry=True)
    result = BacktestResult()
    open_tr: BTTrade | None = None
    ctx = ctx or Context(trade_date="day")

    for i, bar in enumerate(bars_1m):
        decision_ms = bar.ts_ms + 60_000
        view = BarView(bars=bars_1m[: i + 1], decision_ms=decision_ms)

        # feed paper broker path prices
        for px in _fill_path(bar, open_tr.side if open_tr else 1):
            fills = broker.on_tick(symbol, px, bid=px, ask=px)
            for f in fills:
                if open_tr and f.get("purpose") in {"stop", "target", "exit"}:
                    _close_trade(open_tr, f["price"], bar.ts_ms, f.get("purpose") or "exit", broker)
                    result.trades.append(open_tr)
                    state.open_intraday = 0
                    state.open_symbols.discard(symbol)
                    open_tr = None

        if open_tr is not None:
            # check stop/target on bar extremes
            if open_tr.side > 0 and bar.low <= open_tr.stop_init:
                _close_trade(open_tr, open_tr.stop_init, bar.ts_ms, "stop", broker)
                result.trades.append(open_tr)
                state.open_intraday = 0
                state.open_symbols.discard(symbol)
                open_tr = None
            continue

        for strat in strategies:
            if strat.book != "A":
                continue
            for sig in strat.on_bar(symbol, view, ctx):
                result.signals.append(sig)
                ok, _ = can_open(state, sig, limits, decision_ms)
                if not ok:
                    continue
                sz = size(sig.entry_ref, sig.stop, state.capital, limits.risk_per_trade_pct, 0.05, "A", limits)
                if sz.qty <= 0:
                    continue
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
                break
            if open_tr:
                break

    if open_tr is not None:
        last = bars_1m[-1]
        _close_trade(open_tr, last.close, last.ts_ms, "square_off", broker)
        result.trades.append(open_tr)
    return result


# re-export helper used by tests
__all__ = ["BacktestResult", "BTTrade", "run_daily_book", "run_intraday_day", "cost_in_r"]
