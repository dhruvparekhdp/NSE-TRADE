"""Run PREREG trials through lab/evaluate + ledger (PLAN_V2 V3-3 / V-NEXT N2)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.paths import engine_db_path, lake_dir
from core.exits import ExitRules
from data.instruments import parse_nifty100_csv
from data.lake import Lake
from lab.backtest import run_daily_book
from lab.baselines import simulate_baselines_from_signals
from lab.ledger import connect, data_hash_for, record_trial, trial_count
from lab.market_filters import block_f1_vol, block_f2_trend, nifty_closes_to_date
from lab.trial_metrics import HALF_MID_MS, full_trial_report
from strategies.base import Context
from strategies.registry import ALL, get
from strategies.swing_breakout import bars_from_daily_df

PREREG = [
    ("T1_S6_swing", "S6_swing", None),
    ("T2_S6b_keltner", "S6b_keltner", None),
    ("T3_F1_vol", "S6_swing", "F1"),
    ("T4_F2_trend", "S6_swing", "F2"),
    ("T5_S7_xsmom", "S7_xsmom", None),
]

NIFTY_SYMBOLS = ("NIFTY", "NIFTY 50", "NIFTY50", "NIFTYBEES")
VIX_SYMBOLS = ("INDIAVIX", "INDIA VIX", "INDIAVIX ")


def _lake_symbols(lake: Lake) -> list[str]:
    root = lake.root / "bars_1d"
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.parquet"))


def _universe_symbols(lake: Lake) -> list[str]:
    nifty_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nse" / "nifty100.csv"
    config_path = Path(__file__).resolve().parent.parent / "config" / "ind_nifty100list.csv"
    for p in (config_path, nifty_path):
        if p.exists():
            want = set(parse_nifty100_csv(p.read_text(encoding="utf-8")))
            have = set(_lake_symbols(lake))
            picked = sorted(want & have)
            if picked:
                return picked
    return _lake_symbols(lake)


def _pick_series(lake: Lake, names: tuple[str, ...]) -> list:
    from strategies.swing_breakout import bars_from_daily_df

    for n in names:
        df = lake.read_daily(n)
        if df is not None and not getattr(df, "empty", True):
            return bars_from_daily_df(df.to_dict(orient="records"))
    return []


def _ctx_factory(filter_code: str | None, nifty_bars: list):
    def factory(i: int, _daily_bars, _view):
        ctx = Context(trade_date=str(i))
        if not filter_code or not nifty_bars:
            return ctx
        closes = nifty_closes_to_date(nifty_bars, min(i, len(nifty_bars) - 1))
        if filter_code == "F1" and block_f1_vol(closes):
            ctx.extras["block_new_entries"] = True
        if filter_code == "F2" and block_f2_trend(closes):
            ctx.extras["block_new_entries"] = True
        return ctx

    return factory


def run_one(
    prereg_id: str,
    strategy_id: str,
    filter_code: str | None,
    lake: Lake,
    symbols: list[str],
    db: Path,
    *,
    nifty_bars: list,
    vix_by_date: dict[int, float],
) -> dict:
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
    ctx_factory = _ctx_factory(filter_code, nifty_bars)
    for sym in symbols:
        daily = lake.read_daily(sym)
        if daily is None or getattr(daily, "empty", True):
            continue
        bars = bars_from_daily_df(daily.to_dict(orient="records"))
        bt = run_daily_book(
            symbol=sym,
            daily_bars=bars,
            strategy=strat,
            capital=100_000.0,
            limits=None,
            ctx_factory=ctx_factory if filter_code else None,
        )
        picks.extend([t for t in bt.trades if t.role == "pick"])
        m, r = simulate_baselines_from_signals(bt.signals, bars, rules)
        mirrors.extend(m)
        randoms.extend(r)
    report = full_trial_report(
        prereg_id,
        strategy_id,
        picks,
        mirrors,
        randoms,
        mid_ms=HALF_MID_MS,
        vix_by_date=vix_by_date,
    )
    conn = connect(db)
    record_trial(
        conn,
        strategy=strategy_id,
        params={"prereg_id": prereg_id, "filter": filter_code},
        data_from="lake",
        data_to="lake",
        period="2012-2026",
        n=len(picks),
        avg_r=report["avg_r"],
        win_pct=(sum(1 for t in picks if t.r_mult > 0) / len(picks) * 100.0) if picks else 0.0,
        passed=report["passed"],
        prereg_id=prereg_id,
        data_hash=data_hash_for(json.dumps({"n": len(picks), "symbols": symbols}, sort_keys=True)),
        post_hoc=False,
    )
    report["trials_total"] = trial_count(conn)
    if report["passed"]:
        report["verdict"] = "pass"
    elif "n_first" in report.get("gate_reasons", []):
        report["verdict"] = "insufficient_n"
    else:
        report["verdict"] = "gate_fail"
    conn.close()
    return report


def vix_close_by_date(lake: Lake) -> dict[int, float]:
    for n in VIX_SYMBOLS:
        df = lake.read_daily(n)
        if df is None or getattr(df, "empty", True):
            continue
        out: dict[int, float] = {}
        for _, row in df.iterrows():
            out[int(row["date"])] = float(row["close"])
        return out
    return {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default=None)
    p.add_argument("--db", default=None)
    p.add_argument("--symbols", default=None, help="comma list; default lake ∩ Nifty100")
    p.add_argument("--trials", default="T1,T2,T3,T4,T5", help="subset or T6 for open-entry trial")
    args = p.parse_args(argv)
    lake = Lake(Path(args.lake or lake_dir()))
    db = Path(args.db or engine_db_path())
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else _universe_symbols(lake)
    )
    nifty_bars = _pick_series(lake, NIFTY_SYMBOLS)
    vix_map = vix_close_by_date(lake)
    want = {x.strip() for x in args.trials.split(",") if x.strip()}
    rows = []
    catalog = list(PREREG)
    if "T6" in want or "T6_S6_open" in want:
        catalog.append(("T6_S6_open", "S6_swing_open", None))
    for pid, sid, filt in catalog:
        key = pid.split("_")[0]
        if want and key not in want and pid not in want:
            continue
        rows.append(run_one(pid, sid, filt, lake, symbols, db, nifty_bars=nifty_bars, vix_by_date=vix_map))
    out = Path(args.lake or lake_dir()).parent / "reports" / "prereg_v3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"report": str(out), "symbols": len(symbols), "rows": rows}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
