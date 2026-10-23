"""Real mirror and random-time baselines (PLAN_V2 V2-4 / B5). Never fabricate R."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from core.exits import ExitRules, virtual_outcome
from core.types import Bar, Signal
from lab.backtest import BTTrade
from strategies.base import mirror, random_baseline


def mirror_signal(sig: Signal) -> Signal:
    return mirror(sig)


def random_signal(sig: Signal, window_start_ms: int, window_end_ms: int) -> Signal:
    return random_baseline(sig, window_start_ms, window_end_ms)


def simulate_baseline(
    sig: Signal,
    bars: list[Bar],
    rules: ExitRules,
) -> BTTrade | None:
    """Run the shared exit engine on a baseline signal; None if no_fill."""
    out = virtual_outcome(sig, bars, rules)
    if out.get("status") != "closed":
        return None
    risk = abs(sig.entry_ref - sig.stop)
    return BTTrade(
        symbol=sig.symbol,
        strategy=sig.strategy,
        book=sig.book,
        side=sig.side,
        qty=1,
        entry_ms=bars[0].ts_ms if bars else sig.ts_ms,
        entry_price=sig.entry_ref,
        stop_init=sig.stop,
        exit_ms=out.get("exit_ms"),
        exit_price=out.get("exit_price"),
        exit_reason=out.get("reason"),
        r_mult=float(out.get("r") or 0.0),
        role=sig.role,
        net_inr=float(out.get("r") or 0.0) * risk,
    )


def gate_beats(
    picks: Iterable[BTTrade],
    mirrors: Iterable[BTTrade],
    randoms: Iterable[BTTrade],
) -> tuple[bool, bool]:
    """True if mean pick R beats mean mirror and mean random (both required)."""

    def avg(xs: Iterable[BTTrade]) -> float:
        rows = list(xs)
        return sum(t.r_mult for t in rows) / len(rows) if rows else 0.0

    ap, am, ar = avg(picks), avg(mirrors), avg(randoms)
    return ap > am, ap > ar


def deterministic_seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16)
