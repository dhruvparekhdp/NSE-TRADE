"""Technical indicators used by strategies (plan A10 / P2-2). Pure numpy/pandas-free loops for clarity."""

from __future__ import annotations

from collections.abc import Sequence


def sma(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0 or not values:
        return out
    alpha = 2.0 / (n + 1)
    prev: float | None = None
    for i, v in enumerate(values):
        if prev is None:
            if i >= n - 1:
                prev = sum(values[: n]) / n
                out[i] = prev
            continue
        prev = alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def wilder_rma(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    avg = sum(values[:n]) / n
    out[n - 1] = avg
    for i in range(n, len(values)):
        avg = (avg * (n - 1) + values[i]) / n
        out[i] = avg
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    n: int = 14,
) -> list[float | None]:
    trs: list[float] = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
    return wilder_rma(trs, n)


def rsi(closes: Sequence[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[1 : n + 1]) / n
    avg_l = sum(losses[1 : n + 1]) / n
    out[n] = 100.0 if avg_l == 0 else 100.0 - (100.0 / (1.0 + avg_g / avg_l))
    for i in range(n + 1, len(closes)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
        out[i] = 100.0 if avg_l == 0 else 100.0 - (100.0 / (1.0 + avg_g / avg_l))
    return out


def session_vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(len(closes)):
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += typical * volumes[i]
        cum_v += volumes[i]
        out[i] = None if cum_v <= 0 else cum_pv / cum_v
    return out


def opening_range(highs: Sequence[float], lows: Sequence[float]) -> tuple[float, float]:
    return max(highs), min(lows)


def donchian_high(highs: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(highs)
    for i in range(len(highs)):
        if i + 1 >= n:
            out[i] = max(highs[i + 1 - n : i + 1])
    return out


def keltner(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    n: int = 20,
    atr_mult: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    mid = ema(closes, n)
    a = atr(highs, lows, closes, n)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is not None and a[i] is not None:
            upper[i] = mid[i] + atr_mult * a[i]  # type: ignore[operator]
            lower[i] = mid[i] - atr_mult * a[i]  # type: ignore[operator]
    return mid, upper, lower
