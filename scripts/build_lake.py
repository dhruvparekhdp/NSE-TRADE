"""Build daily lake from var/bhav + optional corp actions (V-NEXT N1).

  python -m scripts.build_lake --bhav var/bhav --lake var/lake
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.paths import lake_dir
from data.instruments import parse_nifty100_csv
from data.lake import Lake
from data.lake_build import ingest_bhav_dir, load_corp_actions, write_data_health_markdown


def _default_symbols() -> list[str]:
    nifty_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nse" / "nifty100.csv"
    if nifty_path.exists():
        return parse_nifty100_csv(nifty_path.read_text(encoding="utf-8"))
    from data.instruments import NIFTY100_SEED

    return list(NIFTY100_SEED)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bhav", default="var/bhav")
    p.add_argument("--lake", default=None)
    p.add_argument("--corp", default="config/corp_actions.csv")
    p.add_argument("--report", default="var/reports/data_health.md")
    args = p.parse_args(argv)
    corp_path = Path(args.corp)
    actions = load_corp_actions(corp_path)
    lake = Lake(Path(args.lake or lake_dir()))
    stats = ingest_bhav_dir(lake, Path(args.bhav), corp_actions=actions)
    bars_dir = lake.root / "bars_1d"
    symbols = sorted(p.stem for p in bars_dir.glob("*.parquet")) if bars_dir.exists() else _default_symbols()
    summary = write_data_health_markdown(
        lake,
        symbols=symbols[:200] if len(symbols) > 200 else symbols,
        out_path=Path(args.report),
        corp_actions_applied=bool(actions),
        build=stats,
    )
    json_path = Path(args.report).with_suffix(".json")
    json_path.write_text(json.dumps({"build": stats.__dict__, "health": summary}, indent=2), encoding="utf-8")
    print(json.dumps({"stats": stats.__dict__, "report": str(args.report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
