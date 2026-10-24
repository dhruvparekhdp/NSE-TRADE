"""PREREG trial breakdown tables (V-NEXT N2 / plan A11)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from lab.backtest import BTTrade
from lab.evaluate import _avg_r, gate, split_by_date

IST = ZoneInfo("Asia/Kolkata")

# PREREG.md fixed halves
HALF_MID_MS = int(datetime(2019, 1, 1, 0, 0, tzinfo=IST).timestamp() * 1000)


def _year_ms(y: int) -> tuple[int, int]:
    start = int(datetime(y, 1, 1, tzinfo=IST).timestamp() * 1000)
    end = int(datetime(y + 1, 1, 1, tzinfo=IST).timestamp() * 1000)
    return start, end


def exit_mix(trades: list[BTTrade]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for t in trades:
        r = t.exit_reason or "unknown"
        c[r] += 1
    return dict(c)


def by_year(trades: list[BTTrade]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for y in range(2012, 2030):
        lo, hi = _year_ms(y)
        part = [t for t in trades if lo <= t.entry_ms < hi]
        if not part:
            continue
        out[str(y)] = {
            "n": len(part),
            "avg_r": _avg_r(part),
            "net_inr": sum(t.net_inr for t in part),
        }
    return out


def vix_terciles(
    trades: list[BTTrade],
    vix_close_by_date: dict[int, float],
) -> dict[str, dict[str, float]]:
    """Bucket trades by India VIX close on entry day (YYYYMMDD int keys)."""
    if not vix_close_by_date or not trades:
        return {}
    vals = sorted(vix_close_by_date.values())
    if len(vals) < 3:
        return {}
    t1 = vals[len(vals) // 3]
    t2 = vals[(2 * len(vals)) // 3]

    def bucket(v: float) -> str:
        if v <= t1:
            return "low"
        if v <= t2:
            return "mid"
        return "high"

    groups: dict[str, list[BTTrade]] = {"low": [], "mid": [], "high": []}
    for t in trades:
        d = datetime.fromtimestamp(t.entry_ms / 1000, tz=IST)
        key = int(d.strftime("%Y%m%d"))
        v = vix_close_by_date.get(key)
        if v is None:
            continue
        groups[bucket(v)].append(t)
    return {
        k: {"n": len(v), "avg_r": _avg_r(v), "net_inr": sum(x.net_inr for x in v)}
        for k, v in groups.items()
        if v
    }


def cost_summary(trades: list[BTTrade]) -> dict[str, float]:
    if not trades:
        return {"avg_cost_r": 0.0, "total_net_inr": 0.0}
    cost_rs = []
    for t in trades:
        risk = abs(t.entry_price - t.stop_init) * t.qty or 1.0
        cost_rs.append(t.costs_inr / risk)
    return {
        "avg_cost_r": sum(cost_rs) / len(cost_rs),
        "total_net_inr": sum(t.net_inr for t in trades),
    }


def full_trial_report(
    prereg_id: str,
    strategy_id: str,
    picks: list[BTTrade],
    mirrors: list[BTTrade],
    randoms: list[BTTrade],
    *,
    mid_ms: int | None = None,
    vix_by_date: dict[int, float] | None = None,
) -> dict:
    mid = mid_ms if mid_ms is not None else HALF_MID_MS
    g = gate(strategy_id, picks, mirrors, randoms, book="B", mid_ms=mid)
    first, second = split_by_date(picks, mid)
    m1, m2 = split_by_date(mirrors, mid)
    r1, r2 = split_by_date(randoms, mid)
    return {
        "prereg_id": prereg_id,
        "strategy": strategy_id,
        "n": len(picks),
        "n_first": len(first),
        "n_second": len(second),
        "avg_r_first": _avg_r(first),
        "avg_r_second": _avg_r(second),
        "avg_r": _avg_r(picks),
        "beat_mirror_first": g.beat_mirror_first,
        "beat_mirror_second": g.beat_mirror_second,
        "beat_random_first": g.beat_random_first,
        "beat_random_second": g.beat_random_second,
        "mirror_avg_first": _avg_r(m1),
        "mirror_avg_second": _avg_r(m2),
        "random_avg_first": _avg_r(r1),
        "random_avg_second": _avg_r(r2),
        "avg_r_stress": g.avg_r_stress,
        "passed": g.passed,
        "gate_reasons": g.reasons,
        "by_year": by_year(picks),
        "exit_mix": exit_mix(picks),
        "cost": cost_summary(picks),
        "vix_terciles": vix_terciles(picks, vix_by_date or {}),
    }


def gate_report_to_md_row(r: dict) -> str:
    return (
        f"| {r['prereg_id']} | {r['n']} | {r['avg_r_first']:.3f} | {r['avg_r_second']:.3f} | "
        f"{'Y' if r['beat_mirror_first'] and r['beat_mirror_second'] else 'N'} | "
        f"{'Y' if r['beat_random_first'] and r['beat_random_second'] else 'N'} | "
        f"{r['avg_r_stress']:.3f} | {'PASS' if r['passed'] else 'fail'} |"
    )
