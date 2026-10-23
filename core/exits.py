"""Shared fill / exit engine for lab, paper, and outcomes (PLAN_V2 V2-7 / D6)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from core.types import Bar, Signal

Product = Literal["MIS", "CNC"]


@dataclass
class ExitRules:
    product: Product = "CNC"
    slippage_pct: float = 0.05  # CNC default; MIS often 0.03
    stop_extra_slip_pct: float = 0.05  # PLAN A9.5 extra on stops
    trail_atr_mult: float = 2.5
    max_sessions: int = 20
    # Strategies set entry_ref to the LIMIT price (PLAN A10 close×1.005 is applied upstream).
    entry_limit_offset_pct: float = 0.0
    square_off_ms: int | None = None  # intraday engine square-off (UTC ms)


@dataclass
class Position:
    symbol: str
    strategy: str
    book: str
    side: int
    qty: int
    entry_ms: int
    entry_price: float
    stop_init: float
    stop: float
    risk_inr: float
    target: float | None = None
    sessions_held: int = 0
    highest_close: float | None = None
    lowest_close: float | None = None


@dataclass(frozen=True)
class ExitEvent:
    reason: str
    price: float
    ts_ms: int


@dataclass(frozen=True)
class EntryFill:
    price: float
    ts_ms: int
    reason: str = "limit"


def _slip(px: float, side: int, *, pct: float, is_exit: bool) -> float:
    """Adverse slippage: buys pay up, sells receive less."""
    if is_exit:
        # long exit = sell → price down; short exit = buy → price up
        return px * (1 - pct / 100.0) if side > 0 else px * (1 + pct / 100.0)
    return px * (1 + pct / 100.0) if side > 0 else px * (1 - pct / 100.0)


def limit_price(signal: Signal, *, offset_pct: float = 0.5) -> float:
    """Next-day buy limit from signal close reference (PLAN A10 / V2-1)."""
    if signal.side > 0:
        return signal.entry_ref * (1 + offset_pct / 100.0)
    return signal.entry_ref * (1 - offset_pct / 100.0)


def fill_entry(order: Signal, bar: Bar, rules: ExitRules | None = None) -> EntryFill | None:
    """Fill next-day LIMIT if the bar trades through it (V2-1 / B4).

    Fill at min(open, limit) for longs (better if open below) + slippage; else no_fill.
    """
    rules = rules or ExitRules()
    lim = limit_price(order, offset_pct=rules.entry_limit_offset_pct)
    if order.side > 0:
        if bar.low > lim:
            return None
        raw = min(bar.open, lim)
        px = _slip(raw, 1, pct=rules.slippage_pct, is_exit=False)
        return EntryFill(price=px, ts_ms=bar.ts_ms, reason="limit")
    # short: limit below ref; fill if high >= limit
    if bar.high < lim:
        return None
    raw = max(bar.open, lim)
    px = _slip(raw, -1, pct=rules.slippage_pct, is_exit=False)
    return EntryFill(price=px, ts_ms=bar.ts_ms, reason="limit")


def _stop_fill_price(pos: Position, bar: Bar, rules: ExitRules) -> tuple[float, str]:
    """If open gaps through stop → fill at open; else at stop. Both get slip + stop extra."""
    stop = pos.stop
    extra = rules.slippage_pct + rules.stop_extra_slip_pct
    if pos.side > 0:
        if bar.open <= stop:
            return _slip(bar.open, 1, pct=extra, is_exit=True), "stop_gap"
        return _slip(stop, 1, pct=extra, is_exit=True), "stop"
    if bar.open >= stop:
        return _slip(bar.open, -1, pct=extra, is_exit=True), "stop_gap"
    return _slip(stop, -1, pct=extra, is_exit=True), "stop"


def step_exits(
    pos: Position,
    bar: Bar,
    rules: ExitRules,
    *,
    atr: float | None = None,
) -> tuple[Position, ExitEvent | None]:
    """One bar of exit management: gap/stop, target, trail, time, square-off."""
    pos = replace(pos)
    pos.sessions_held += 1
    if pos.highest_close is None:
        pos.highest_close = bar.close
        pos.lowest_close = bar.close
    else:
        pos.highest_close = max(pos.highest_close, bar.close)
        pos.lowest_close = min(pos.lowest_close or bar.close, bar.close)

    # Stop (entry day included — conservative)
    hit_stop = (pos.side > 0 and bar.low <= pos.stop) or (pos.side < 0 and bar.high >= pos.stop)
    if hit_stop:
        px, reason = _stop_fill_price(pos, bar, rules)
        return pos, ExitEvent(reason=reason, price=px, ts_ms=bar.ts_ms)

    # Target
    if pos.target is not None:
        hit_tgt = (pos.side > 0 and bar.high >= pos.target) or (pos.side < 0 and bar.low <= pos.target)
        if hit_tgt:
            px = _slip(pos.target, pos.side, pct=rules.slippage_pct, is_exit=True)
            return pos, ExitEvent(reason="target", price=px, ts_ms=bar.ts_ms)

    # Trail (longs: highest close − k·ATR; shorts: lowest + k·ATR); never loosen
    if atr is not None and atr > 0 and rules.trail_atr_mult > 0:
        if pos.side > 0:
            trail = pos.highest_close - rules.trail_atr_mult * atr
            pos.stop = max(pos.stop, trail)
        else:
            trail = (pos.lowest_close or bar.close) + rules.trail_atr_mult * atr
            pos.stop = min(pos.stop, trail)

    # Time exit
    if pos.sessions_held >= rules.max_sessions:
        px = _slip(bar.close, pos.side, pct=rules.slippage_pct, is_exit=True)
        return pos, ExitEvent(reason="time", price=px, ts_ms=bar.ts_ms)

    # Intraday square-off
    if rules.square_off_ms is not None and bar.ts_ms >= rules.square_off_ms:
        px = _slip(bar.close, pos.side, pct=rules.slippage_pct, is_exit=True)
        return pos, ExitEvent(reason="square_off", price=px, ts_ms=bar.ts_ms)

    return pos, None


def virtual_outcome(
    signal: Signal,
    bars: list[Bar],
    rules: ExitRules,
    *,
    atr_series: list[float] | None = None,
) -> dict[str, Any]:
    """Simulate entry+exits for take/skip scoreboard (same engine as backtest)."""
    if not bars:
        return {"status": "no_bars", "r": None}
    fill = fill_entry(signal, bars[0], rules)
    if fill is None:
        return {"status": "no_fill", "r": None}
    risk_px = abs(fill.price - signal.stop)
    pos = Position(
        symbol=signal.symbol,
        strategy=signal.strategy,
        book=signal.book,
        side=signal.side,
        qty=1,
        entry_ms=fill.ts_ms,
        entry_price=fill.price,
        stop_init=signal.stop,
        stop=signal.stop,
        risk_inr=risk_px,
        target=signal.target,
    )
    for i, bar in enumerate(bars[1:], start=1):
        atr = atr_series[i] if atr_series and i < len(atr_series) else signal.features.get("atr14")
        pos, ev = step_exits(pos, bar, rules, atr=float(atr) if atr else None)
        if ev:
            signed = pos.side
            gross = (ev.price - pos.entry_price) * signed
            r = gross / risk_px if risk_px else 0.0
            return {"status": "closed", "r": r, "reason": ev.reason, "exit_price": ev.price, "exit_ms": ev.ts_ms}
    return {"status": "open", "r": None}
