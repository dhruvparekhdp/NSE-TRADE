"""R9: square-off / no-entry crons come from core.session_times, not fixed 15:05/14:45."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.session_times import derive_engine_times
from engine.runner import EngineRunner


def test_runner_cron_uses_derived_session_times():
    sq, no_entry = derive_engine_times("15:10")
    assert (sq, no_entry) == ("14:55", "14:35")

    r = EngineRunner.__new__(EngineRunner)
    # Only broker cut-off set — derived times must drive the cron (not stale 15:05/14:45).
    r.settings = type(
        "S",
        (),
        {
            "broker_squareoff_at": "15:10",
            "square_off_at": None,
            "no_entry_after": None,
            "strategies_enabled": [],
        },
    )()
    r.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    r._schedule()
    by_id = {j.id: j for j in r.scheduler.get_jobs()}
    # APScheduler trigger string includes hour/minute
    assert "14" in str(by_id["square_off"].trigger) and "55" in str(by_id["square_off"].trigger)
    assert "14" in str(by_id["no_new_entries"].trigger) and "35" in str(by_id["no_new_entries"].trigger)


def test_settings_overrides_win_over_derive():
    r = EngineRunner.__new__(EngineRunner)
    r.settings = type(
        "S",
        (),
        {
            "broker_squareoff_at": "15:10",
            "square_off_at": "14:50",
            "no_entry_after": "14:30",
            "strategies_enabled": [],
        },
    )()
    r.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    r._schedule()
    by_id = {j.id: j for j in r.scheduler.get_jobs()}
    assert "50" in str(by_id["square_off"].trigger)
    assert "30" in str(by_id["no_new_entries"].trigger)
