"""Round prices to the instrument tick (PLAN_V2 V0-4 / B9 / AGENTS §8).

Prefer the scrip-master tick when known; otherwise fall back to NSE price-band
table in config/tick_bands.json (MARKET_INDIA §4).
"""

from __future__ import annotations

import json
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

Direction = Literal["up", "down", "nearest"]

_BANDS_PATH = Path(__file__).resolve().parent.parent / "config" / "tick_bands.json"


@lru_cache(maxsize=1)
def _bands() -> list[tuple[float | None, float]]:
    raw = json.loads(_BANDS_PATH.read_text(encoding="utf-8"))
    out: list[tuple[float | None, float]] = []
    for row in raw["bands"]:
        out.append((row["price_lt"], float(row["tick"])))
    return out


def tick_for_price(price: float) -> float:
    """Fallback tick from NSE price bands when scrip-master tick is unknown."""
    for price_lt, tick in _bands():
        if price_lt is None or price < price_lt:
            return tick
    return 0.05


def round_to_tick(price: float, tick: float, direction: Direction = "nearest") -> float:
    """Snap `price` onto a multiple of `tick`.

    Buy limits use "up", sell limits use "down", stop triggers use "toward market"
    (caller picks up/down). Uses Decimal so 1234.56 / 0.10 is exact.
    """
    if tick <= 0:
        raise ValueError(f"tick must be positive, got {tick}")
    p = Decimal(str(price))
    t = Decimal(str(tick))
    units = p / t
    if direction == "up":
        snapped = units.to_integral_value(rounding=ROUND_CEILING) * t
    elif direction == "down":
        snapped = units.to_integral_value(rounding=ROUND_FLOOR) * t
    else:
        snapped = units.to_integral_value(rounding=ROUND_HALF_UP) * t
    # Normalise -0.0 and trim float junk for common ticks
    return float(snapped)


def round_buy_limit(price: float, tick: float | None = None) -> float:
    t = tick if tick is not None else tick_for_price(price)
    return round_to_tick(price, t, "up")


def round_sell_limit(price: float, tick: float | None = None) -> float:
    t = tick if tick is not None else tick_for_price(price)
    return round_to_tick(price, t, "down")


def round_stop_trigger(price: float, *, side: int, tick: float | None = None) -> float:
    """Round stop trigger toward the market (long: up, short: down)."""
    t = tick if tick is not None else tick_for_price(price)
    return round_to_tick(price, t, "up" if side > 0 else "down")
