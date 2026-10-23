"""V6-2: late / out-of-order ticks amend the correct minute within slack."""

from __future__ import annotations

from data.bars import BarBuilder, Tick, minute_floor_ms


def test_late_tick_within_slack_updates_prior_minute():
    b = BarBuilder(late_slack_ms=5_000)
    t0 = 1_700_000_000_000
    m0 = minute_floor_ms(t0)
    b.on_tick(Tick("SBIN", m0 + 10_000, 100.0), now_ms=m0 + 10_000)
    # roll to next minute
    closed = b.on_tick(Tick("SBIN", m0 + 60_000 + 1_000, 101.0), now_ms=m0 + 60_000 + 1_000)
    assert closed and closed[0].ts_ms == m0
    # late tick for m0 within slack
    b.on_tick(Tick("SBIN", m0 + 59_000, 102.0), now_ms=m0 + 60_000 + 3_000)
    assert b.finished[0].high >= 102.0 or b.finished[0].close == 102.0


def test_reconnect_backoff_sequence():
    from data.stream import reconnect_backoff

    assert reconnect_backoff(0) == 1
    assert reconnect_backoff(4) == 30
    assert reconnect_backoff(99) == 30
