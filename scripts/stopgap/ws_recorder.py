"""Angel WebSocket recorder (stopgap until ticket C6 puts this in the engine). Never places an order.

Subscribes the Nifty 100 + NIFTY 50 / NIFTY BANK / INDIA VIX in QUOTE mode, builds 1-minute bars from ticks
(OHLC from last traded price, volume = change in the day's cumulative traded volume) and appends each finished
bar as one JSON line to var/ws/bars_1m_<YYYYMMDD>.jsonl. Status every minute in var/ws/status.json.
One login per run; never re-logs in (a failed login ends the run). Stops by itself at 15:31 IST.
Run from ~/nse-engine:  nohup .venv/bin/python var/ws/ws_recorder.py >> var/ws/recorder.log 2>&1 &
"""
import json, logging, os, signal, sqlite3, sys, threading, time
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
logging.getLogger("smart_connect").disabled = True
from config.secrets_loader import apply_db_secrets
apply_db_secrets()
from config.settings import get_settings
from broker.smartconnect_factory import build_smart_connect, totp_now_utc
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

IST = ZoneInfo("Asia/Kolkata")
OUT = Path("var/ws"); OUT.mkdir(parents=True, exist_ok=True)
_today = datetime.now(IST).date()
_hol = {h["date"] for h in json.loads(Path(f"config/holidays_{_today.year}.json").read_text()).get("holidays", [])} \
    if Path(f"config/holidays_{_today.year}.json").exists() else set()
if _today.weekday() >= 5 or _today.isoformat() in _hol:
    print(f"{_today} is not a trading day; recorder not started", flush=True)
    sys.exit(0)
STOP_MIN = 15 * 60 + 31
db = sqlite3.connect("file:var/engine.db?mode=ro", uri=True)
NAMES = dict(db.execute("SELECT token, symbol FROM instruments WHERE in_universe=1 AND token != ''").fetchall())
db.close()
NAMES.update({"99926000": "NIFTY 50", "99926009": "NIFTY BANK", "99926017": "INDIA VIX"})
# names the portal expects in var/quotes_cache.json (web/portal_data.build_market looks for "NIFTY")
QUOTE_NAME = {"NIFTY 50": "NIFTY", "NIFTY BANK": "BANKNIFTY", "INDIA VIX": "INDIAVIX"}
CACHE = Path("var/quotes_cache.json")


def say(msg):
    print(f"{datetime.now(IST):%H:%M:%S} {msg}", flush=True)


s = get_settings()
api = build_smart_connect()
code = s.angel_client_code.get_secret_value().strip()
r = api.generateSession(code, s.angel_pin.get_secret_value().strip(),
                        totp_now_utc("".join(s.angel_totp_secret.get_secret_value().split()).upper())) or {}
if not r.get("status"):
    say(f"login failed, stopping: {r.get('errorcode')} {r.get('message')}")
    sys.exit(1)
jwt, feed = r["data"]["jwtToken"], api.getfeedToken()
say(f"login ok; subscribing {len(NAMES)} instruments")

lock = threading.Lock()
cur: dict[tuple[str, int], dict] = {}   # (token, minute ms) -> bar being built
last_cv: dict[str, int] = {}            # token -> day's cumulative volume at its previous tick
latest: dict[str, dict] = {}            # token -> latest quote for the portal's quotes cache
stats = {"ticks": 0, "bars": 0, "last_tick": None, "errors": 0, "started": datetime.now(IST).isoformat(timespec="seconds")}


def minute_of(ts_ms):
    return int(ts_ms // 60_000 * 60_000)


def flush(upto_minute_ms):
    """Append every bar whose minute is before upto_minute_ms (finished minutes only)."""
    with lock:
        done = [cur.pop(k) for k in [k for k in cur if k[1] < upto_minute_ms]]
    if not done:
        return
    by_day: dict[str, list] = {}
    for b in done:
        by_day.setdefault(datetime.fromtimestamp(b["m"] / 1000, IST).strftime("%Y%m%d"), []).append(b)
    for day, bars in by_day.items():
        with open(OUT / f"bars_1m_{day}.jsonl", "a") as f:
            for b in sorted(bars, key=lambda x: (x["m"], x["sym"])):
                f.write(json.dumps({"sym": b["sym"], "ts": datetime.fromtimestamp(b["m"] / 1000, IST).isoformat(),
                                    "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "ticks": b["n"],
                                    "src": "angel_ws"}) + "\n")
    stats["bars"] += len(done)


def on_data(wsapp, msg):
    tok = str(msg.get("token"))
    ts = msg.get("exchange_timestamp") or int(time.time() * 1000)
    px = (msg.get("last_traded_price") or 0) / 100
    if px <= 0:
        return
    cv = msg.get("volume_trade_for_the_day")
    key = (tok, minute_of(ts))
    with lock:
        b = cur.get(key)
        if b is None:
            b = cur[key] = {"sym": NAMES.get(tok, tok), "m": key[1], "o": px, "h": px, "l": px, "c": px, "v": 0, "n": 0}
        b["h"] = max(b["h"], px); b["l"] = min(b["l"], px); b["c"] = px; b["n"] += 1
        latest[tok] = {"ltp": px, "open": (msg.get("open_price_of_the_day") or 0) / 100 or None,
                       "high": (msg.get("high_price_of_the_day") or 0) / 100 or None,
                       "low": (msg.get("low_price_of_the_day") or 0) / 100 or None,
                       "prev_close": (msg.get("closed_price") or 0) / 100 or None, "volume": cv, "ts_ms": ts}
        if cv is not None:
            if tok in last_cv and cv >= last_cv[tok]:
                b["v"] += cv - last_cv[tok]     # first tick of the day only sets the baseline
            last_cv[tok] = cv
        stats["ticks"] += 1
        stats["last_tick"] = datetime.fromtimestamp(ts / 1000, IST).isoformat(timespec="seconds")


def write_quotes_cache():
    """Same shape as data/free_quotes.write_quotes_cache, all instruments, atomic replace."""
    with lock:
        snap = dict(latest)
    if not snap:
        return
    quotes = []
    for tok, q in snap.items():
        name = NAMES.get(tok, tok)
        prev = q["prev_close"]
        quotes.append({"symbol": QUOTE_NAME.get(name, name), **q, "source": "angel_ws",
                       "chg_pct": (q["ltp"] / prev - 1) * 100 if prev else None})
    quotes.sort(key=lambda x: (x["symbol"] not in ("NIFTY", "BANKNIFTY", "INDIAVIX"), x["symbol"]))
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"ts_ms": int(time.time() * 1000), "quotes": quotes, "source": "angel_ws"}))
    os.replace(tmp, CACHE)


ws = SmartWebSocketV2(jwt, s.angel_api_key.get_secret_value(), code, feed, max_retry_attempt=5, retry_delay=5)


def on_open(wsapp):
    say("websocket open"); ws.subscribe("rec", SmartWebSocketV2.QUOTE, [{"exchangeType": 1, "tokens": list(NAMES)}])


def on_error(wsapp, err):
    stats["errors"] += 1; say(f"ws error: {str(err)[:150]}")


ws.on_open, ws.on_data, ws.on_error = on_open, on_data, on_error
ws.on_close = lambda *a: say("websocket closed")
threading.Thread(target=ws.connect, daemon=True).start()
# nohup/background jobs ignore SIGINT; make `kill <pid>` (SIGTERM) flush the open bars and log out
signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))

try:
    while True:
        time.sleep(5)
        now = datetime.now(IST)
        flush(minute_of(time.time() * 1000))          # write every bar from earlier minutes
        write_quotes_cache()                          # portal ticker / watchlist / Nifty card
        if now.second < 5:
            (OUT / "status.json").write_text(json.dumps({**stats, "open_bars": len(cur), "at": now.isoformat(timespec="seconds")}))
            say(f"ticks {stats['ticks']} bars {stats['bars']} last tick {stats['last_tick']}")
        if now.hour * 60 + now.minute >= STOP_MIN:
            break
finally:
    flush(10 ** 15)
    try:
        ws.close_connection()
    except Exception:  # noqa: BLE001
        pass
    try:
        api.terminateSession(code)
    except Exception:  # noqa: BLE001
        pass
    say(f"stopped: {stats}")
