"""F1a: Angel ONE_DAY → lake + corporate jump flag."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from data.angel_daily import (
    CORP_JUMP_PCT,
    detect_corp_jumps,
    job_daily_bars,
    rows_to_daily_frame,
)
from data.lake import Lake


class FakeDailyAPI:
    def __init__(self, rows: list[list]) -> None:
        self.rows = rows
        self.calls: list[dict] = []

    def get_candle_data(self, payload: dict) -> list[list]:
        self.calls.append(payload)
        return self.rows


def test_detect_corp_jump_flags_large_move():
    frame = rows_to_daily_frame(
        [
            ["2024-01-02T00:00:00+05:30", 100, 101, 99, 100, 1],
            ["2024-01-03T00:00:00+05:30", 100, 101, 99, 140, 1],
        ]
    )
    hits = detect_corp_jumps(frame, "X", threshold_pct=CORP_JUMP_PCT)
    assert len(hits) == 1
    assert hits[0]["symbol"] == "X"


def test_job_daily_bars_writes_lake_and_events(tmp_path: Path):
    lake = Lake(tmp_path / "lake")
    from engine.state import init_db

    conn = init_db(tmp_path / "e.db")
    api = FakeDailyAPI(
        [
            ["2024-01-02T00:00:00+05:30", 800, 810, 790, 805, 1000],
            ["2024-01-03T00:00:00+05:30", 805, 820, 800, 815, 1100],
        ]
    )
    stats = job_daily_bars(
        lake,
        conn,
        symbols=[("SBIN", "3045")],
        trade_date=date(2024, 1, 3),
        api=api,
        sleep_s=0.0,
        backfill_sessions=2,
    )
    assert stats["symbols_ok"] >= 1
    daily = lake.read_daily("SBIN")
    assert len(daily) >= 2
    assert api.calls and api.calls[0]["interval"] == "ONE_DAY"
    assert api.calls[0]["exchange"] == "NSE"
