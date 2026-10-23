"""Daily paper/live vs replay comparison (plan A12.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParityResult:
    trade_date: str
    matched: int
    signals_live: int
    signals_replay: int
    avg_fill_diff_pct: float
    faults: list[str]

    @property
    def ok(self) -> bool:
        return not self.faults


def compare_trades(live: list[dict[str, Any]], replay: list[dict[str, Any]], tol_pct: float = 0.05) -> ParityResult:
    faults: list[str] = []
    # key by symbol+strategy+side+minute
    def key(t: dict[str, Any]) -> tuple:
        return (t.get("symbol"), t.get("strategy"), t.get("side"), t.get("entry_ms"))

    live_map = {key(t): t for t in live}
    replay_map = {key(t): t for t in replay}
    matched = 0
    diffs = []
    for k, lt in live_map.items():
        rt = replay_map.get(k)
        if rt is None:
            faults.append(f"extra_live:{k}")
            continue
        matched += 1
        lp = float(lt.get("entry_price") or 0)
        rp = float(rt.get("entry_price") or 0)
        if lp:
            diffs.append(abs(lp - rp) / lp * 100.0)
    for k in replay_map:
        if k not in live_map:
            faults.append(f"missing_live:{k}")
    avg = sum(diffs) / len(diffs) if diffs else 0.0
    if avg > tol_pct:
        faults.append(f"fill_diff:{avg:.4f}")
    return ParityResult(
        trade_date=str((live or replay or [{}])[0].get("trade_date") or ""),
        matched=matched,
        signals_live=len(live),
        signals_replay=len(replay),
        avg_fill_diff_pct=avg,
        faults=faults,
    )
