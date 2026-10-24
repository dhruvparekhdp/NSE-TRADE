"""Part 3: offline strategy + event-study smoke (no network)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab.event_study import EventPoint, summarise_events
from lab.market_filters import block_f1_vol, block_f2_trend
from strategies.registry import ALL as STRATEGIES


def _fixture_closes() -> dict[str, list[tuple[int, float]]]:
    """Synthetic drop + partial rebound for EMUDRA-style event."""
    base = 20260401
    closes = [100.0, 92.0, 90.0, 91.5, 93.0, 94.0, 95.0, 96.0]
    dates = [base + i for i in range(len(closes))]
    return {"EMUDRA": list(zip(dates, closes, strict=True))}


def run_event_smoke() -> dict:
    events = [
        EventPoint("EMUDRA", 20260402, -0.7, "cyber_breach"),
    ]
    data = {k: v for k, v in _fixture_closes().items()}
    summary = summarise_events(events, data)
    return {"event_study": summary}


def run_filter_smoke() -> dict:
    nifty = [100 + i * 0.1 for i in range(280)]
    return {
        "f1_block": block_f1_vol(nifty),
        "f2_block": block_f2_trend(nifty),
        "strategies_registered": sorted(STRATEGIES.keys()),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prereg", action="store_true", help="also run run_prereg_trials if lake exists")
    p.add_argument("--lake", type=Path, default=None)
    args = p.parse_args()
    report = {"filters": run_filter_smoke(), "events": run_event_smoke()}
    if args.prereg:
        lake = args.lake or Path("var/lake")
        if lake.exists():
            from scripts.run_prereg_trials import main as prereg_main

            prereg_main(["--lake", str(lake), "--trials", "T1"])
            report["prereg"] = str(lake.parent / "reports" / "prereg_v3.json")
        else:
            report["prereg"] = "skipped_no_lake"
    out = Path("var/reports/strategy_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), **report}, indent=2))
    ok = report["events"]["event_study"].get("cyber_breach", {}).get("n", 0) >= 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
