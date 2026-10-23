"""Split/bonus adjustment factors (PLAN_V2 V1-7). Strategies use adjusted; costs use raw."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CorpAction:
    symbol: str
    ex_date: date
    factor: float  # multiply prices before ex_date by factor to adjust forward
    kind: str = "bonus"


def adj_factor_on(
    symbol: str,
    d: date,
    actions: list[CorpAction],
) -> float:
    """Cumulative factor to bring a raw price on date `d` to today-adjusted terms."""
    f = 1.0
    for a in actions:
        if a.symbol.upper() != symbol.upper():
            continue
        if d < a.ex_date:
            f *= a.factor
    return f


def adjust_close(raw_close: float, symbol: str, d: date, actions: list[CorpAction]) -> float:
    return raw_close * adj_factor_on(symbol, d, actions)
