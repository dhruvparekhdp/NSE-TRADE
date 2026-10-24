"""PREREG F1/F2 entry filters on Nifty daily series (T3/T4)."""

from __future__ import annotations

import math

from core.indicators import sma
from core.types import Bar


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
    """Rank of latest 20d vol vs past 252 session vols (PREREG T3)."""
    if len(closes) < 273:
        return None
    current = realised_vol(closes)
    if current is None:
        return None
    hist: list[float] = []
    for end in range(len(closes) - 252, len(closes)):
        seg = closes[: end + 1]
        v = realised_vol(seg)
        if v is not None:
            hist.append(v)
    if not hist:
        return None
    below = sum(1 for v in hist if v <= current)
    return below / len(hist)


def block_f1_vol(closes: list[float], *, max_rank: float = 0.667) -> bool:
    rank = vol_rank_252(closes)
    return rank is not None and rank > max_rank


def block_f2_trend(closes: list[float]) -> bool:
    s = sma(closes, 200)
    if s[-1] is None or closes[-1] is None:
        return False
    return closes[-1] < s[-1]


def nifty_closes_to_date(nifty_bars: list[Bar], upto_index: int) -> list[float]:
    return [b.close for b in nifty_bars[: upto_index + 1]]
