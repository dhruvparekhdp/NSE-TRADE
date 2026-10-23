"""One-shot: print Angel key flags + full watchlist (run on server or against local APIs)."""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("NSE_BASE", "http://127.0.0.1:8090")
PW = os.environ.get("ADMIN_PASSWORD", "")


def main() -> int:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    if PW:
        req = urllib.request.Request(
            f"{BASE}/api/login",
            data=json.dumps({"password": PW}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req) as r:
            print("login:", r.status, r.read().decode()[:80])

    print("=== KEYS ===")
    with opener.open(f"{BASE}/api/keys") as r:
        rows = json.load(r).get("rows") or []
    for row in rows:
        print(
            f"{row['key']:28} set={row.get('is_set')}  where={row.get('where')}  {row.get('hint') or ''}"
        )

    print("\n=== HEALTH ===")
    with opener.open(f"{BASE}/api/health") as r:
        print(json.dumps(json.load(r), indent=2))

    print("\n=== TODAY ===")
    with opener.open(f"{BASE}/api/today") as r:
        print(json.dumps(json.load(r), indent=2))

    print("\n=== WATCHLIST ===")
    with opener.open(f"{BASE}/api/quotes") as r:
        data = json.load(r)
    qs = data.get("quotes") or []
    print(f"source={data.get('source')}  ts_ms={data.get('ts_ms')}  n={len(qs)}")
    print(f"{'SYM':12} {'LTP':>10} {'OPEN':>10} {'HIGH':>10} {'LOW':>10} {'PREV':>10} {'VOL':>12} SRC")
    for q in qs:
        print(
            f"{q['symbol']:12} {q['ltp']:10.2f} {q.get('open') or 0:10.2f} "
            f"{q.get('high') or 0:10.2f} {q.get('low') or 0:10.2f} "
            f"{q.get('prev_close') or 0:10.2f} {q.get('volume') or 0:12} {q.get('source')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
