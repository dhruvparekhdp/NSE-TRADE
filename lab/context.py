"""Intraday context + timeframe resample for Book A (PLAN_V2 V2-2 / B14/B15; review R6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.types import Bar
from data.bars import resample
from strategies.base import Context

IST = ZoneInfo("Asia/Kolkata")


def _hm(ts_ms: int) -> int:
    t = datetime.fromtimestamp(ts_ms / 1000, tz=IST).timetz().replace(tzinfo=None)
    return t.hour * 60 + t.minute


def timeframe_minutes(tf: str) -> int:
    t = (tf or "1m").lower()
    if t.endswith("m"):
        return int(t[:-1] or "1")
    if t.endswith("h"):
        return int(t[:-1] or "1") * 60
    if t in {"1d", "d", "day", "daily"}:
        return 375  # continuous session length; callers usually pass daily bars
    return 1


def bars_for_strategy(bars_1m: list[Bar], strategy_tf: str) -> list[Bar]:
    """Resample 1m → strategy timeframe before on_bar (B14)."""
    mins = timeframe_minutes(strategy_tf)
    if mins <= 1:
        return list(bars_1m)
    return resample(bars_1m, mins)


def slot_vol_avg(prior_days_1m: list[list[Bar]], decision_ms: int, lookback_days: int = 20) -> float | None:
    """Average volume at the same minute-of-day over prior sessions."""
    slot = _hm(decision_ms)
    vols: list[float] = []
    for day_bars in prior_days_1m[-lookback_days:]:
        for b in day_bars:
            if _hm(b.ts_ms) == slot:
                vols.append(float(b.volume))
                break
    if not vols:
        return None
    return sum(vols) / len(vols)


def cross_sectional_ranks(
    symbol_rets: dict[str, float],
) -> tuple[dict[str, int], dict[str, int]]:
    """ret_decile (1–10) and rs_rank (1 = strongest) across the universe."""
    if not symbol_rets:
        return {}, {}
    ordered = sorted(symbol_rets.items(), key=lambda kv: kv[1])
    n = len(ordered)
    ret_decile: dict[str, int] = {}
    rs_rank: dict[str, int] = {}
    for i, (sym, _) in enumerate(ordered):
        # weakest → decile 1; strongest → 10
        ret_decile[sym] = 1 if n == 1 else int(round(i / (n - 1) * 9)) + 1
        # rs_rank 1 = strongest
        rs_rank[sym] = n - i
    return ret_decile, rs_rank


def build_intraday_context(
    *,
    trade_date: str,
    symbol: str,
    prev_close: float | None,
    pdh: float | None,
    open_px: float | None,
    decision_ms: int,
    prior_days_1m: list[list[Bar]] | None = None,
    universe_session_rets: dict[str, float] | None = None,
    extras: dict[str, Any] | None = None,
) -> Context:
    """Fill prev_close, pdh, gap_pct, slot_vol_avg, ret_decile, rs_rank (B15)."""
    gap_pct = None
    if prev_close and open_px and prev_close > 0:
        gap_pct = (open_px - prev_close) / prev_close * 100.0
    slot = slot_vol_avg(prior_days_1m or [], decision_ms)
    deciles, ranks = cross_sectional_ranks(universe_session_rets or {})
    ex: dict[str, Any] = {
        "prev_close": prev_close,
        "pdh": pdh,
        "gap_pct": gap_pct,
        "slot_vol_avg": slot,
        "ret_decile": deciles.get(symbol),
        "rs_rank": ranks.get(symbol),
    }
    if extras:
        ex.update(extras)
    return Context(trade_date=trade_date, extras=ex)
