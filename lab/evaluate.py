"""Split history, baselines, cost stress, gate (plan A11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lab.backtest import BTTrade


@dataclass
class GateReport:
    strategy: str
    n_first: int
    n_second: int
    avg_r_first: float
    avg_r_second: float
    avg_r_stress: float
    beat_mirror_first: bool
    beat_mirror_second: bool
    beat_random_first: bool
    beat_random_second: bool
    passed: bool
    reasons: list[str]


def _avg_r(trades: list[BTTrade]) -> float:
    if not trades:
        return 0.0
    return sum(t.r_mult for t in trades) / len(trades)


def split_by_date(trades: list[BTTrade], mid_ms: int) -> tuple[list[BTTrade], list[BTTrade]]:
    first = [t for t in trades if t.entry_ms < mid_ms]
    second = [t for t in trades if t.entry_ms >= mid_ms]
    return first, second


def gate(
    strategy: str,
    picks: list[BTTrade],
    mirrors: list[BTTrade],
    randoms: list[BTTrade],
    *,
    book: str = "B",
    mid_ms: int,
) -> GateReport:
    """All must hold (plan A11). Book B n>=100/half; Book A n>=200/half."""
    min_n = 100 if book == "B" else 200
    first, second = split_by_date(picks, mid_ms)
    m1, m2 = split_by_date(mirrors, mid_ms)
    r1, r2 = split_by_date(randoms, mid_ms)
    reasons: list[str] = []
    # R4 / B5: empty baselines must not silently look like avg R = 0 (beating them is free).
    if not mirrors:
        reasons.append("empty_mirrors")
    if not randoms:
        reasons.append("empty_randoms")
    avg1, avg2 = _avg_r(first), _avg_r(second)
    if avg1 < 0.10:
        reasons.append("avg_r_first")
    if avg2 < 0.10:
        reasons.append("avg_r_second")
    if len(first) < min_n:
        reasons.append("n_first")
    if len(second) < min_n:
        reasons.append("n_second")
    beat_m1 = bool(mirrors) and avg1 > _avg_r(m1)
    beat_m2 = bool(mirrors) and avg2 > _avg_r(m2)
    beat_r1 = bool(randoms) and avg1 > _avg_r(r1)
    beat_r2 = bool(randoms) and avg2 > _avg_r(r2)
    if mirrors and not beat_m1:
        reasons.append("mirror_first")
    if mirrors and not beat_m2:
        reasons.append("mirror_second")
    if randoms and not beat_r1:
        reasons.append("random_first")
    if randoms and not beat_r2:
        reasons.append("random_second")
    # cost stress: haircut net by 1.5x costs → approx scale R by costs ratio
    stressed = []
    for t in picks:
        gross = t.gross_inr
        costs = t.costs_inr * 1.5
        net = gross - costs
        risk = abs(t.entry_price - t.stop_init) * t.qty or 1.0
        stressed.append(net / risk)
    avg_stress = sum(stressed) / len(stressed) if stressed else 0.0
    if avg_stress <= 0:
        reasons.append("cost_stress")
    return GateReport(
        strategy=strategy,
        n_first=len(first),
        n_second=len(second),
        avg_r_first=avg1,
        avg_r_second=avg2,
        avg_r_stress=avg_stress,
        beat_mirror_first=beat_m1,
        beat_mirror_second=beat_m2,
        beat_random_first=beat_r1,
        beat_random_second=beat_r2,
        passed=not reasons,
        reasons=reasons,
    )


def shuffle_outcomes(trades: list[BTTrade], seed: int = 1) -> list[BTTrade]:
    """Null test helper: permute R outcomes."""
    import random

    rs = [t.r_mult for t in trades]
    rng = random.Random(seed)
    rng.shuffle(rs)
    out = []
    for t, r in zip(trades, rs, strict=True):
        out.append(
            BTTrade(
                symbol=t.symbol,
                strategy=t.strategy,
                book=t.book,
                side=t.side,
                qty=t.qty,
                entry_ms=t.entry_ms,
                entry_price=t.entry_price,
                stop_init=t.stop_init,
                exit_ms=t.exit_ms,
                exit_price=t.exit_price,
                exit_reason=t.exit_reason,
                gross_inr=t.gross_inr,
                costs_inr=t.costs_inr,
                net_inr=t.net_inr,
                r_mult=r,
                role=t.role,
            )
        )
    return out


def report_to_dict(g: GateReport) -> dict[str, Any]:
    return g.__dict__.copy()
