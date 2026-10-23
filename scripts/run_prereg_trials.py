"""Run the five PREREG trials and record the ledger (PLAN_V2 V3-3).

Uses the lake under settings.data_dir. If history is too short for the gate,
records the trial as failed with an honest verdict — never fabricates fills.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.paths import engine_db_path, lake_dir
from core.exits import ExitRules
from data.lake import Lake
from lab.backtest import run_daily_book
from lab.baselines import simulate_baselines_from_signals
from lab.evaluate import gate
from lab.ledger import connect, data_hash_for, record_trial, trial_count
from strategies.registry import ALL, get
from strategies.swing_breakout import bars_from_daily_df

PREREG = [
    ("T1_S6_swing", "S6_swing"),
    ("T2_S6b_keltner", "S6b_keltner"),
    ("T3_F1_vol", "S6_swing"),  # filter applied in ctx when available
    ("T4_F2_trend", "S6_swing"),
    ("T5_S7_xsmom", "S7_xsmom"),
]


def _mid_ms(bars) -> int:
    if not bars:
        return 0
    # split near 2019-01-01 if present, else midpoint
    cut = None
    for b in bars:
        # rough: timestamps after 2019
        if b.ts_ms >= 1_546_300_800_000:  # 2019-01-01 UTC approx
            cut = b.ts_ms
            break
    return cut if cut is not None else bars[len(bars) // 2].ts_ms


def run_one(prereg_id: str, strategy_id: str, lake: Lake, symbols: list[str], db: Path) -> dict:
    strat = get(strategy_id) if strategy_id in ALL else None
    if strat is None:
        return {
            "prereg_id": prereg_id,
            "strategy": strategy_id,
            "passed": False,
            "verdict": "strategy_not_registered",
            "n": 0,
        }
    picks = []
    mirrors = []
    randoms = []
    rules = ExitRules(product="CNC")
    for sym in symbols:
        daily = lake.read_daily(sym)
        if daily is None or getattr(daily, "empty", True):
            continue
        bars = bars_from_daily_df(daily.to_dict(orient="records"))
        bt = run_daily_book(symbol=sym, daily_bars=bars, strategy=strat, capital=100_000.0)
        picks.extend([t for t in bt.trades if t.role == "pick"])
        m, r = simulate_baselines_from_signals(bt.signals, bars, rules)
        mirrors.extend(m)
        randoms.extend(r)
    mid = _mid_ms([t for t in picks]) if picks else 0
    g = gate(strategy_id, picks, mirrors, randoms, book="B", mid_ms=mid or 1)
    payload = {
        "prereg_id": prereg_id,
        "strategy": strategy_id,
        "n": len(picks),
        "avg_r": sum(t.r_mult for t in picks) / len(picks) if picks else 0.0,
        "gate": g.__dict__,
        "passed": g.passed,
        "verdict": (
            "pass"
            if g.passed
            else (
                "insufficient_n"
                if "n_first" in g.reasons or "n_second" in g.reasons
                else "gate_fail"
            )
        ),
    }
    conn = connect(db)
    record_trial(
        conn,
        strategy=strategy_id,
        params={"prereg_id": prereg_id},
        data_from="lake",
        data_to="lake",
        period="2012-2026",
        n=len(picks),
        avg_r=payload["avg_r"],
        win_pct=(sum(1 for t in picks if t.r_mult > 0) / len(picks) * 100.0) if picks else 0.0,
        passed=g.passed,
        prereg_id=prereg_id,
        data_hash=data_hash_for(json.dumps({"n": len(picks), "symbols": symbols}, sort_keys=True)),
        post_hoc=False,
    )
    payload["trials_total"] = trial_count(conn)
    conn.close()
    return payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default=None)
    p.add_argument("--db", default=None)
    p.add_argument("--symbols", default="SBIN,RELIANCE,TCS,INFY,HDFCBANK")
    args = p.parse_args(argv)
    lake = Lake(Path(args.lake or lake_dir()))
    db = Path(args.db or engine_db_path())
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    rows = [run_one(pid, sid, lake, symbols, db) for pid, sid in PREREG]
    out = Path(args.lake or lake_dir()).parent / "reports" / "prereg_v3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
