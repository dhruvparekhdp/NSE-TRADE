"""N1: bhav → lake + corporate action adjustment."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from data.corporate_actions import CorpAction
from data.lake import Lake
from data.lake_build import apply_corp_actions, ingest_bhav_dir, load_corp_actions


def test_apply_corp_actions_scales_history(tmp_path: Path):
    import pandas as pd

    df = pd.DataFrame(
        [
            {"date": 20200101, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1, "source": "bhav"},
            {"date": 20200201, "open": 200, "high": 210, "low": 190, "close": 205, "volume": 1, "source": "bhav"},
        ]
    )
    actions = [CorpAction("SBIN", date(2020, 1, 15), 0.5, "bonus")]
    out = apply_corp_actions(df, "SBIN", actions)
    assert out.loc[out["date"] == 20200101, "close"].iloc[0] == 105 * 0.5
    assert out.loc[out["date"] == 20200201, "close"].iloc[0] == 205


def test_ingest_bhav_dir_from_fixture(tmp_path: Path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "nse" / "bhav_sample.csv"
    bhav_dir = tmp_path / "bhav"
    bhav_dir.mkdir()
    (bhav_dir / "bhav_20261022.csv").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    lake = Lake(tmp_path / "lake")
    stats = ingest_bhav_dir(lake, bhav_dir)
    assert stats.files_read == 1
    assert stats.symbols >= 1
    daily = lake.read_daily("SBIN")
    assert len(daily) >= 1


def test_load_corp_actions_missing_returns_empty(tmp_path: Path):
    assert load_corp_actions(tmp_path / "missing.csv") == []
