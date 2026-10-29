"""Rebuild today's morning 1-min bars from NSE's intraday chart JSON (price only), for instruments that have no
Angel backfill. Angel's candle API is rate-blocked for the account (26-28 Oct 2026); the WebSocket recorder only has
bars from its start. NSE gives ~1 price per minute: bar o = previous price, c = this price, h/l = max/min of the two,
v = 0 (unknown), src "nse_chart_price_only". Writes var/ws/bars_1m_<day>_backfill.jsonl (keeps Angel rows already
there). Polite: 1 request/s. Run on the server from ~/nse-engine (stdin)."""
import json, os, sqlite3, sys, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())
from data.nse_http import NseSession

IST = ZoneInfo("Asia/Kolkata")
NSE_SHIFT_MS = 19_800_000           # NSE chart timestamps are IST wall-clock written as UTC epoch
now = datetime.now(IST)
day = now.strftime("%Y%m%d")
live = Path(f"var/ws/bars_1m_{day}.jsonl")
first_live = min((json.loads(l)["ts"] for l in live.open()), default=None) if live.exists() else None
end_ms = int(datetime.fromisoformat(first_live).timestamp() * 1000) if first_live else int(now.timestamp() * 1000)
start_ms = int(now.replace(hour=9, minute=15, second=0, microsecond=0).timestamp() * 1000)
out = Path(f"var/ws/bars_1m_{day}_backfill.jsonl")
keep = [l for l in out.open()] if out.exists() else []
have = {json.loads(l)["sym"] for l in keep}
db = sqlite3.connect("file:var/engine.db?mode=ro", uri=True)
syms = [s for (s,) in db.execute("SELECT symbol FROM instruments WHERE in_universe=1")]
db.close()
nse = NseSession()
rows, ok, empty = list(keep), 0, []
targets = [(s, f"index={quote(s)}EQN&type=symbol") for s in syms if s not in have]
if "NIFTY 50" not in have:
    targets.append(("NIFTY 50", "index=NIFTY%2050&type=index"))
for sym, q in targets:
    try:
        j = nse.get_json(f"https://www.nseindia.com/api/chart-databyindex-dynamic?{q}")
        pts = [(int(p[0]) - NSE_SHIFT_MS, float(p[1])) for p in (j.get("grapthData") or [])]
    except Exception as e:  # noqa: BLE001
        print(f"{sym}: failed {type(e).__name__} {str(e)[:80]}"); pts = []
    pts = sorted(p for p in pts if p[1] > 0)
    if not pts:
        empty.append(sym)
    prev = None
    for ms, px in pts:
        m = ms // 60_000 * 60_000
        if start_ms <= m < end_ms and prev is not None:
            o = prev
            rows.append(json.dumps({"sym": sym, "ts": datetime.fromtimestamp(m / 1000, IST).isoformat(), "o": o,
                                    "h": max(o, px), "l": min(o, px), "c": px, "v": 0, "ticks": None,
                                    "src": "nse_chart_price_only"}) + "\n")
        prev = px
    ok += bool(pts)
    time.sleep(1.0)
tmp = out.with_suffix(".tmp")
tmp.write_text("".join(rows))
os.replace(tmp, out)
print(f"NSE chart backfill: {ok}/{len(targets)} instruments with data, {len(rows)} bars total in {out.name}; "
      f"window 09:15 -> {datetime.fromtimestamp(end_ms / 1000, IST):%H:%M}; empty: {empty[:8]}")
