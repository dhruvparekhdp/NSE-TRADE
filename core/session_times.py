"""Derive engine square-off / no-entry from broker cut-off (PLAN_V2 V1-3 / D4)."""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse(hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(2000, 1, 1, int(h), int(m))


def _fmt(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"


def derive_engine_times(
    broker_squareoff_at: str,
    *,
    squareoff_lead_min: int = 15,
    no_entry_lead_min: int = 20,
) -> tuple[str, str]:
    """Return (square_off_at, no_entry_after) IST strings.

    Engine squares off `squareoff_lead_min` before the broker; no new entries
    another `no_entry_lead_min` before that.
    """
    broker = _parse(broker_squareoff_at)
    sq = broker - timedelta(minutes=squareoff_lead_min)
    no_entry = sq - timedelta(minutes=no_entry_lead_min)
    if sq >= broker:
        raise ValueError("engine square-off must be before broker cut-off")
    if no_entry >= sq:
        raise ValueError("no-entry must be before engine square-off")
    return _fmt(sq), _fmt(no_entry)
