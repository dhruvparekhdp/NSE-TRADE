"""Book B paper cycle jobs (PLAN_V2 V4-6). Uses shared exits; strategies_enabled empty = shadow-only."""

from __future__ import annotations

import logging
from typing import Any

from core.exits import ExitRules, fill_entry, step_exits, virtual_outcome
from core.types import Bar, Signal

log = logging.getLogger(__name__)


def eod_fill_pending(
    pending: list[Signal],
    bars: dict[str, Bar],
    rules: ExitRules | None = None,
) -> list[dict[str, Any]]:
    """Apply today's daily bar to pending LIMIT entries (job_eod_fill)."""
    rules = rules or ExitRules(product="CNC", entry_limit_offset_pct=0.0)
    out: list[dict[str, Any]] = []
    for sig in pending:
        bar = bars.get(sig.symbol)
        if bar is None:
            out.append({"signal": sig, "status": "no_bar"})
            continue
        fill = fill_entry(sig, bar, rules)
        out.append({"signal": sig, "status": "filled" if fill else "no_fill", "fill": fill})
    return out


def resolve_outcomes(
    signals: list[Signal],
    bars_by_symbol: dict[str, list[Bar]],
    rules: ExitRules | None = None,
) -> list[dict[str, Any]]:
    """virtual_outcome for take/skip/mirror/random (job_outcomes)."""
    rules = rules or ExitRules(product="CNC")
    rows: list[dict[str, Any]] = []
    for sig in signals:
        bars = bars_by_symbol.get(sig.symbol) or []
        rows.append({"signal_id": getattr(sig, "id", None), "role": sig.role, **virtual_outcome(sig, bars, rules)})
    return rows
