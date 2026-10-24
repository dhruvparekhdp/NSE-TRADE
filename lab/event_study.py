"""Event-day returns and rebound stats (V8-P3; no live orders)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventPoint:
    symbol: str
    event_date: int  # YYYYMMDD session date
    severity: float
    event_type: str


def session_return(closes: list[float], idx: int) -> float | None:
    if idx <= 0 or idx >= len(closes):
        return None
    if closes[idx - 1] <= 0:
        return None
    return closes[idx] / closes[idx - 1] - 1.0


def car_horizon(closes: list[float], idx: int, days: int) -> float | None:
    """Close-to-close return from event session close through +days sessions."""
    if idx + days >= len(closes) or closes[idx] <= 0:
        return None
    return closes[idx + days] / closes[idx] - 1.0


def rebound_within(closes: list[float], idx: int, days: int, *, pct: float = 0.02) -> bool | None:
    """True if close at idx+days is at least pct above the post-event trough."""
    if idx + days >= len(closes):
        return None
    trough = min(closes[idx : idx + days + 1])
    if trough <= 0:
        return None
    return closes[idx + days] >= trough * (1.0 + pct)


def summarise_events(
    events: list[EventPoint],
    closes_by_symbol: dict[str, list[tuple[int, float]]],
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10, 20),
) -> dict[str, Any]:
    """Aggregate CAR and rebound rates per event_type."""
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        series = closes_by_symbol.get(ev.symbol)
        if not series:
            continue
        dates = [d for d, _ in series]
        closes = [c for _, c in series]
        try:
            idx = dates.index(ev.event_date)
        except ValueError:
            continue
        row: dict[str, Any] = {
            "symbol": ev.symbol,
            "event_date": ev.event_date,
            "day0_ret": session_return(closes, idx),
        }
        for h in horizons:
            row[f"car_{h}d"] = car_horizon(closes, idx, h)
            row[f"rebound_{h}d"] = rebound_within(closes, idx, h)
        by_type.setdefault(ev.event_type, []).append(row)
    summary: dict[str, Any] = {}
    for et, rows in by_type.items():
        n = len(rows)
        if n == 0:
            continue
        summary[et] = {
            "n": n,
            "avg_day0_ret": _avg([r["day0_ret"] for r in rows]),
            **{f"avg_car_{h}d": _avg([r.get(f"car_{h}d") for r in rows]) for h in horizons},
            **{
                f"pct_rebound_{h}d": _pct_true([r.get(f"rebound_{h}d") for r in rows])
                for h in horizons
            },
        }
    return summary


def _avg(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def _pct_true(vals: list[bool | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    if not xs:
        return None
    return sum(1 for v in xs if v) / len(xs)
