"""Book A shadow signals on live 1m bars (PLAN_V2 V6-3). Never places paper/live orders."""

from __future__ import annotations

from typing import Any

from core.exits import ExitRules, virtual_outcome
from core.types import Bar, Signal
from strategies.base import BarView, Context, Strategy


def shadow_scan(
    *,
    symbol: str,
    bars_1m: list[Bar],
    strategies: list[Strategy],
    decision_ms: int,
    ctx: Context | None = None,
) -> list[Signal]:
    """Run Book A strategies with decision=shadow. Recording only while book_a_mode=shadow."""
    view = BarView(bars=bars_1m, decision_ms=decision_ms, timeframe="1m")
    ctx = ctx or Context(trade_date="shadow")
    out: list[Signal] = []
    for strat in strategies:
        if strat.book != "A":
            continue
        for sig in strat.on_bar(symbol, view, ctx):
            sig.role = "pick"
            # features carry shadow flag for the portal / ledger
            sig.features = {**sig.features, "decision": "shadow", "book_a_mode": "shadow"}
            out.append(sig)
    return out


def shadow_outcomes(signals: list[Signal], bars: list[Bar]) -> list[dict[str, Any]]:
    rules = ExitRules(product="MIS", slippage_pct=0.03, square_off_ms=None)
    return [virtual_outcome(s, bars, rules) for s in signals]
