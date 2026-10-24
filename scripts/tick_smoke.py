"""Offline smoke: synthetic ticks → 1s + 1m bars (no Angel network)."""

from __future__ import annotations

import argparse
import json

from data.bars import Tick, minute_floor_ms, second_floor_ms
from data.tick_pipeline import MultiBarFeed


def main() -> int:
    p = argparse.ArgumentParser(description="1s/1m tick pipeline smoke")
    p.add_argument("--symbol", default="SBIN")
    p.add_argument("--ticks", type=int, default=125, help="synthetic ticks (~2 minutes at 1/s)")
    args = p.parse_args()
    base = 1_700_000_000_000
    feed = MultiBarFeed()
    for i in range(args.ticks):
        ts = base + i * 1_000
        ltp = 100.0 + i * 0.01
        feed.on_tick(
            Tick(args.symbol, ts, ltp, volume_traded=1000 + i, bid=ltp - 0.05, ask=ltp + 0.05),
            now_ms=ts,
        )
    feed.flush(args.symbol)
    sec_keys = {second_floor_ms(b.ts_ms) for b in feed.closed_1s}
    min_keys = {minute_floor_ms(b.ts_ms) for b in feed.closed_1m}
    print(
        json.dumps(
            {
                "ticks": feed.ticks_seen,
                "bars_1s": len(feed.closed_1s),
                "bars_1m": len(feed.closed_1m),
                "unique_seconds": len(sec_keys),
                "unique_minutes": len(min_keys),
                "ok": len(feed.closed_1s) >= args.ticks - 2 and len(feed.closed_1m) >= 1,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
