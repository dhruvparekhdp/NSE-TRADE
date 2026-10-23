"""Results / event window helpers (blocks entries when flagged)."""

from __future__ import annotations

from datetime import date


def in_results_window(today: date, results_dates: set[date], window_days: int = 3) -> bool:
    """True if a results date falls within ±window_days of today."""
    for d in results_dates:
        if abs((d - today).days) <= window_days:
            return True
    return False


def expand_results(csv_dates: list[str]) -> set[date]:
    return {date.fromisoformat(x) for x in csv_dates}
