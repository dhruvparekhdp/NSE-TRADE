"""Fill today's 1-min bars from 09:15 up to the recorder's first minute, via Angel ONE_MINUTE candles.
Same JSON shape as var/ws/bars_1m_<day>.jsonl (src "angel_hist"), written to var/ws/bars_1m_<day>_backfill.jsonl.
~1 request/s; stops at the FIRST refusal (26 Oct 2026: the candle API rate-blocked the account). One login.
Run on the server from ~/nse-engine (stdin)."""
import json, logging, os, sqlite3, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        if k.strip() != "TZ":
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
import logzero
logzero.loglevel(logging.CRITICAL)
logging.disable(logging.CRITICAL)
from config.secrets_loader import apply_db_secrets
apply_db_secrets()
from config.settings import get_settings
from engine.angel_session import angel_login

IST = ZoneInfo("Asia/Kolkata")
now = datetime.now(IST)
day = now.strftime("%Y%m%d")
live = Path(f"var/ws/bars_1m_{day}.jsonl")
first_live = min((json.loads(l)["ts"] for l in live.open()), default=None) if live.exists() else None
end = datetime.fromisoformat(first_live).replace(tzinfo=None) if first_live else now.replace(tzinfo=None)
db = sqlite3.connect("file:var/engine.db?mode=ro", uri=True)
names = dict(db.execute("SELECT token, symbol FROM instruments WHERE in_universe=1 AND token != ''").fetchall())
db.close()
names.update({"99926000": "NIFTY 50", "99926009": "NIFTY BANK", "99926017": "INDIA VIX"})
s = get_settings()
api = angel_login(s)
out = Path(f"var/ws/bars_1m_{day}_backfill.jsonl")
have = {json.loads(l)["sym"] for l in out.open()} if out.exists() else set()   # resume: keep finished instruments
PACE_S = float(os.environ.get("PACE_S", "4"))
done = n_bars = 0
try:
    with out.open("a") as f:
        for tok, sym in names.items():
            if sym in have:
                done += 1
                continue
            try:
                r = api.getCandleData({"exchange": "NSE", "symboltoken": tok, "interval": "ONE_MINUTE",
                                       "fromdate": now.strftime("%Y-%m-%d 09:15"), "todate": end.strftime("%Y-%m-%d %H:%M")}) or {}
            except Exception as e:  # noqa: BLE001 - SDK raises on the plain-text "Access denied" body
                print(f"REFUSED after {done} instruments: {str(e)[:120]}"); break
            if not r.get("status"):
                print(f"REFUSED after {done} instruments: {r.get('errorcode')} {r.get('message')}"); break
            for ts, o, h, l, c, v in r.get("data") or []:
                if ts < end.strftime("%Y-%m-%dT%H:%M"):          # stop before the recorder's first minute
                    f.write(json.dumps({"sym": sym, "ts": ts, "o": o, "h": h, "l": l, "c": c, "v": v, "ticks": None,
                                        "src": "angel_hist"}) + "\n")
                    n_bars += 1
            done += 1
            time.sleep(PACE_S)
    print(f"backfill: {done}/{len(names)} instruments, {n_bars} bars, 09:15 -> {end:%H:%M} into {out}")
finally:
    api.terminateSession(s.angel_client_code.get_secret_value())
