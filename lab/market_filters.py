"""PREREG F1/F2 filters — logged skip reasons on Book B scan (V-FIX-2 F1b)."""

from __future__ import annotations

import math

from core.indicators import sma


def realised_vol(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window + 1:
        return None
    rets = []
    for i in range(-window, 0):
        if closes[i - 1] <= 0:
            continue
        rets.append(math.log(closes[i] / closes[i - 1]))
    if len(rets) < window // 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252)


def vol_rank_252(closes: list[float]) -> float | None:
    if len(closes) < 273:
        return None
    current = realised_vol(closes)
    if current is None:
        return None
    hist: list[float] = []
    for end in range(len(closes) - 252, len(closes)):
        v = realised_vol(closes[: end + 1])
        if v is not None:
            hist.append(v)
    if not hist:
        return None
    below = sum(1 for v in hist if v <= current)
    return below / len(hist)


def f1_skip_reason(closes: list[float], *, max_rank: float = 0.667) -> str | None:
    rank = vol_rank_252(closes)
    if rank is not None and rank > max_rank:
        return "market_filter_f1_vol"
    return None


def f2_skip_reason(closes: list[float]) -> str | None:
    s = sma(closes, 200)
    if s[-1] is None:
        return None
    if closes[-1] < s[-1]:
        return "market_filter_f2_trend"
    return None
