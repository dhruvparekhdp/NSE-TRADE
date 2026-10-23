"""Run a strategy through the lab and record a trial (plan A11).

  python -m scripts.research --strategy S6_swing --symbol SBIN
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.paths import engine_db_path, lake_dir
from data.lake import Lake
from lab.backtest import run_daily_book
from lab.evaluate import gate
from lab.ledger import connect, record_trial, trial_count
from strategies.registry import get
from strategies.swing_breakout import bars_from_daily_df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True)
    p.add_argument("--symbol", default="SBIN")
    p.add_argument("--lake", default=None, help="default: settings.data_dir/lake")
    p.add_argument("--db", default=None, help="default: settings.data_dir/engine.db")
    p.add_argument("--capital", type=float, default=50_000.0)
    args = p.parse_args(argv)
    if args.lake is None:
        args.lake = str(lake_dir())
    if args.db is None:
        args.db = str(engine_db_path())

    lake = Lake(Path(args.lake))
    daily = lake.read_daily(args.symbol)
    if daily.empty:
        print(f"no daily bars for {args.symbol} in {args.lake}")
        return 1
    bars = bars_from_daily_df(daily.to_dict(orient="records"))
    strat = get(args.strategy)
    bt = run_daily_book(symbol=args.symbol, daily_bars=bars, strategy=strat, capital=args.capital)
    picks = [t for t in bt.trades if t.role == "pick"]
    # V2-4 / B5: never fabricate mirror R = −pick or random R = 0.
    # Real baselines use lab.baselines.simulate_baseline on the same bars (wired in V3 trials).
    mirrors: list = []
    randoms: list = []
    mid = bars[len(bars) // 2].ts_ms if bars else 0
    g = gate(args.strategy, picks, mirrors, randoms, book=strat.book, mid_ms=mid)
    out_dir = Path(args.lake).parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.strategy}_{args.symbol}.json"
    payload = {
        "strategy": args.strategy,
        "symbol": args.symbol,
        "n_trades": len(picks),
        "avg_r": sum(t.r_mult for t in picks) / len(picks) if picks else 0.0,
        "gate": g.__dict__,
        "trades": [t.__dict__ for t in picks[:50]],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    conn = connect(args.db)
    record_trial(
        conn,
        strategy=args.strategy,
        params={},
        data_from=str(daily["date"].iloc[0]),
        data_to=str(daily["date"].iloc[-1]),
        period="full",
        n=len(picks),
        avg_r=payload["avg_r"],
        win_pct=(sum(1 for t in picks if t.r_mult > 0) / len(picks) * 100.0) if picks else 0.0,
        passed=g.passed,
        report_path=str(out),
    )
    print(json.dumps({
        "report": str(out),
        "gate_passed": g.passed,
        "trials": trial_count(conn, args.strategy),
        "n_trades": payload["n_trades"],
        "avg_r": payload["avg_r"],
    }, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
