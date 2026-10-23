"""Cross-sectional S7 ranking (PREREG T5 / review R10)."""

from __future__ import annotations

import math
from statistics import mean, pstdev

from core.indicators import atr


def _zscores(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    xs = list(values.values())
    mu = mean(xs)
    sd = pstdev(xs) if len(xs) > 1 else 1.0
    if sd <= 0:
        sd = 1.0
    return {k: (v - mu) / sd for k, v in values.items()}


def momentum_score(closes: list[float]) -> float | None:
    """Mean of z-scores of 6m and 12m return ÷ daily-return volatility (T5)."""
    if len(closes) < 252:
        return None
    ret6 = closes[-1] / closes[-126] - 1.0
    ret12 = closes[-1] / closes[-252] - 1.0
    daily = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
    vol = math.sqrt(sum(x * x for x in daily[-60:]) / max(1, len(daily[-60:]))) or 1e-6
    return (ret6 / vol + ret12 / vol) / 2.0


def rank_universe(closes_by_symbol: dict[str, list[float]]) -> list[tuple[str, float]]:
    raw: dict[str, float] = {}
    for sym, closes in closes_by_symbol.items():
        sc = momentum_score(closes)
        if sc is not None:
            raw[sym] = sc
    z = _zscores(raw)
    return sorted(z.items(), key=lambda kv: kv[1], reverse=True)


def pick_symbols(
    ranked: list[tuple[str, float]],
    *,
    capital: float,
    min_position_cnc_inr: float,
) -> set[str]:
    n = max(1, int(capital // min_position_cnc_inr))
    return {sym for sym, _ in ranked[:n]}


def exit_symbols(
    ranked: list[tuple[str, float]],
    holdings: set[str],
    *,
    capital: float,
    min_position_cnc_inr: float,
) -> set[str]:
    """Holdings that fell out of the top 2N at rebalance (T5)."""
    n = max(1, int(capital // min_position_cnc_inr))
    keep = {sym for sym, _ in ranked[: 2 * n]}
    return {h for h in holdings if h not in keep}


def atr20_stop(highs: list[float], lows: list[float], closes: list[float]) -> float | None:
    a = atr(highs, lows, closes, 20)[-1]
    if a is None or not closes:
        return None
    return closes[-1] - 3.0 * a
