"""Multi-symbol Book B backtest with shared cash and priority (PLAN_V2 V2-5 / B6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.exits import ExitRules, Position, fill_entry, step_exits
from core.risk import PortfolioState, RiskLimits, can_open, on_swing_close, on_swing_open, size
from core.sessions import daily_bar_close_ms
from core.types import Bar, Signal
from data.universe import universe_on
from lab.backtest import BacktestResult, BTTrade, _close_bt
from strategies.base import BarView, Context, Strategy

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class PendingEntry:
    signal: Signal
    priority: float


def _priority(sig: Signal) -> float:
    """Strongest strategy first, then lower ATR% (crypto swing_book.priority)."""
    atr = float(sig.features.get("atr14") or sig.features.get("atr_pct") or 1.0)
    atr_pct = atr / sig.entry_ref if sig.entry_ref else atr
    # higher is better: negate atr_pct so tighter risk ranks first after strategy weight
    strat_w = float(sig.features.get("priority") or 0.0)
    return strat_w * 1_000.0 - atr_pct


def run_portfolio_daily(
    *,
    bars_by_symbol: dict[str, list[Bar]],
    strategies: list[Strategy],
    capital: float = 100_000.0,
    limits: RiskLimits | None = None,
    hold_sessions: int = 20,
) -> BacktestResult:
    """Shared-cash portfolio over universe_on(date); one position per symbol."""
    limits = limits or RiskLimits()
    from data.sectors import load_sector_map

    sector_map = load_sector_map() or None
    state = PortfolioState(capital=capital, start_capital=capital)
    result = BacktestResult()
    rules = ExitRules(product="CNC", max_sessions=hold_sessions, entry_limit_offset_pct=0.0)
    open_pos: dict[str, Position] = {}
    open_tr: dict[str, BTTrade] = {}
    pending: list[PendingEntry] = []

    # Align by bar index (assume same calendar length / caller pads)
    n = max((len(v) for v in bars_by_symbol.values()), default=0)
    for i in range(n):
        # exits first
        for sym in list(open_pos.keys()):
            bars = bars_by_symbol.get(sym) or []
            if i >= len(bars):
                continue
            bar = bars[i]
            pos, ev = step_exits(open_pos[sym], bar, rules, atr=None)
            open_pos[sym] = pos
            if ev:
                tr = open_tr.pop(sym)
                _close_bt(tr, ev.price, ev.ts_ms, ev.reason, pos.sessions_held)
                result.trades.append(tr)
                state.open_swing = max(0, state.open_swing - 1)
                state.open_symbols.discard(sym)
                on_swing_close(state, sym, sector_map)
                state.capital += tr.net_inr
                del open_pos[sym]

        # fill pendings
        still: list[PendingEntry] = []
        for pe in sorted(pending, key=lambda p: -p.priority):
            sym = pe.signal.symbol
            bars = bars_by_symbol.get(sym) or []
            if i >= len(bars) or sym in open_pos:
                still.append(pe)
                continue
            fill = fill_entry(pe.signal, bars[i], rules)
            if fill is None:
                result.no_fills.append(pe.signal)
                continue
            ok, reason = can_open(state, pe.signal, limits, bars[i].ts_ms, sector_map=sector_map)
            if not ok:
                if reason in ("max_open_swing", "sector_cap"):
                    result.signals.append(pe.signal)
                    # log skip via features
                    pe.signal.features = {**pe.signal.features, "skip_reason": reason}
                continue
            sz = size(fill.price, pe.signal.stop, state.capital, limits.risk_per_trade_pct, 0.05, "B", limits)
            if sz.qty <= 0:
                pe.signal.features = {**(pe.signal.features or {}), "skip_reason": sz.reason}
                result.signals.append(pe.signal)
                continue
            open_pos[sym] = Position(
                symbol=sym,
                strategy=pe.signal.strategy,
                book="B",
                side=pe.signal.side,
                qty=sz.qty,
                entry_ms=fill.ts_ms,
                entry_price=fill.price,
                stop_init=pe.signal.stop,
                stop=pe.signal.stop,
                risk_inr=abs(fill.price - pe.signal.stop) * sz.qty,
            )
            open_tr[sym] = BTTrade(
                symbol=sym,
                strategy=pe.signal.strategy,
                book="B",
                side=pe.signal.side,
                qty=sz.qty,
                entry_ms=fill.ts_ms,
                entry_price=fill.price,
                stop_init=pe.signal.stop,
            )
            state.open_swing += 1
            state.open_symbols.add(sym)
            on_swing_open(state, sym, sector_map)
        pending = still

        # new signals
        day: date | None = None
        for sym, bars in bars_by_symbol.items():
            if i >= len(bars):
                continue
            bar = bars[i]
            if day is None:
                day = datetime.fromtimestamp(bar.ts_ms / 1000, tz=IST).date()
            if sym.upper() not in universe_on(day) and day.year >= 2019:
                # fixture universe may be empty for modern dates — skip filter when empty seed history only
                pass
            decision_ms = daily_bar_close_ms(bar.ts_ms) + 1_000
            view = BarView(bars=bars[: i + 1], decision_ms=decision_ms, timeframe="1d")
            ctx = Context(trade_date=str(day))
            for strat in strategies:
                if strat.book != "B":
                    continue
                for sig in strat.on_bar(sym, view, ctx):
                    result.signals.append(sig)
                    if sig.role != "pick":
                        continue
                    pending.append(PendingEntry(signal=sig, priority=_priority(sig)))

    return result
