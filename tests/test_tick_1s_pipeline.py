"""Part 1: 1-second tick rollup and multi-resolution feed (no network)."""

from __future__ import annotations

import asyncio

from data.bars import BarBuilder1s, Tick, second_floor_ms
from data.stream import StreamHub
from data.tick_pipeline import MultiBarFeed


def test_second_floor_ms():
    ts = 1_700_000_012_500
    assert second_floor_ms(ts) == second_floor_ms(ts - 500)


def test_1s_bar_closes_on_second_roll():
    bb = BarBuilder1s()
    base = 1_700_000_000_000
    bb.on_tick(Tick("X", base, 10.0), now_ms=base)
    closed = bb.on_tick(Tick("X", base + 1_500, 11.0), now_ms=base + 1_500)
    assert len(closed) == 1
    assert closed[0].open == 10.0
    assert closed[0].close == 10.0


def test_multi_feed_1s_and_1m():
    feed = MultiBarFeed()
    base = 1_700_000_000_000
    for i in range(65):
        ts = base + i * 1_000
        feed.on_tick(Tick("SBIN", ts, 100 + i * 0.1), now_ms=ts)
    assert feed.ticks_seen == 65
    assert len(feed.closed_1s) >= 60
    assert len(feed.closed_1m) >= 1


def test_stream_hub_to_feed():
    loop = asyncio.new_event_loop()
    hub = StreamHub()
    hub.start(loop)
    feed = MultiBarFeed()
    base = 1_700_000_000_000

    async def drain_once() -> None:
        tick = await asyncio.wait_for(hub.queue.get(), timeout=1.0)  # type: ignore[arg-type]
        feed.on_tick(tick)

    hub.push_for_tests(Tick("T", base, 1.0))
    loop.run_until_complete(drain_once())
    assert feed.ticks_seen == 1
    loop.close()
