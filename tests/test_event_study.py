"""Part 3: event study and strategy smoke helpers."""

from __future__ import annotations

from lab.event_study import EventPoint, car_horizon, rebound_within, summarise_events


def test_car_and_rebound_fixture():
    closes = [100.0, 92.0, 90.0, 91.0, 95.0]
    # Event on session 90.0 (idx=2); +2 sessions → 95.0
    assert car_horizon(closes, 2, 2) is not None
    assert car_horizon(closes, 2, 2) > 0
    assert rebound_within(closes, 2, 2) is True


def test_summarise_cyber_breach():
    series = {
        "X": [(20260401, 100.0), (20260402, 90.0), (20260403, 88.0), (20260404, 92.0)],
    }
    ev = [EventPoint("X", 20260402, -0.8, "cyber_breach")]
    s = summarise_events(ev, series, horizons=(1, 2))
    assert s["cyber_breach"]["n"] == 1
