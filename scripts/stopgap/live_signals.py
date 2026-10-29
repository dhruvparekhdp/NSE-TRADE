"""Live Book A SHADOW signals from the recorder's 1-min bars (stopgap until ticket C6). Never places an order.

Every minute until 14:55 IST: read today's bars (var/ws/bars_1m_<day>_backfill.jsonl from Angel candles, then
var/ws/bars_1m_<day>.jsonl from the WebSocket recorder; recorder wins on overlap), run the engine's Book A
strategies exactly as lab/book_a.py does, and store the FIRST signal per strategy x symbol per day in the engine
DB via engine.jobs.persist_signals (book A, decision "shadow"), so the portal's Signals page shows it.
Context: previous close from the live quote cache (WebSocket closed_price), previous-day high and the minute volume
profile from earlier recorder files (only as many days as exist). No Angel calls at all.
Run on the server from ~/nse-engine:  nohup .venv/bin/python -u var/ws/live_signals.py >> var/ws/signals.log 2>&1 &
"""
import json, os, signal as _sig, sqlite3, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())
from core.types import Bar, Signal  # noqa: E402
from data.bars import _agg  # noqa: E402
from engine.jobs import persist_signals  # noqa: E402
from lab.context import build_intraday_context, cross_sectional_ranks, timeframe_minutes  # noqa: E402
from strategies.base import BarView  # noqa: E402
from strategies.registry import ALL  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
WS = Path("var/ws")
DAY = datetime.now(IST)
_hol_f = Path(f"config/holidays_{DAY.year}.json")
_hol = {h["date"] for h in json.loads(_hol_f.read_text()).get("holidays", [])} if _hol_f.exists() else set()
if DAY.weekday() >= 5 or DAY.date().isoformat() in _hol:
    print(f"{DAY.date()} is not a trading day; live signals not started", flush=True)
    sys.exit(0)
D, DK = DAY.date().isoformat(), DAY.strftime("%Y%m%d")
SQ = int(DAY.replace(hour=14, minute=55, second=0, microsecond=0).timestamp() * 1000)
STRATS = [s for s in ALL.values() if s.book == "A"]
_sig.signal(_sig.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))


def say(m):
    print(f"{datetime.now(IST):%H:%M:%S} {m}", flush=True)


def hm(ms):
    t = datetime.fromtimestamp(ms / 1000, IST)
    return t.hour * 60 + t.minute


def load_day(paths):
    """{symbol: [Bar]} from recorder-format JSON lines; later files win on the same (symbol, minute)."""
    by: dict[str, dict[int, Bar]] = {}
    for p in paths:
        if not p.exists():
            continue
        for line in p.open():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ms = int(datetime.fromisoformat(r["ts"]).timestamp() * 1000)
            by.setdefault(r["sym"], {})[ms] = Bar(ms, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), int(r["v"] or 0), "angel")
    return {s: [m[k] for k in sorted(m)] for s, m in by.items()}


# --- prior sessions from earlier recorder files: previous-day high and minute volume profile ---
prior_files = sorted(p for p in WS.glob("bars_1m_2*.jsonl") if "_" not in p.stem[8:] and p.stem[8:] < DK)
prior_days = [load_day([p]) for p in prior_files[-20:]]
pdh = {s: max(b.high for b in bars) for s, bars in (prior_days[-1].items() if prior_days else [])}
vprof: dict[str, list[dict[int, float]]] = {}
for dd in prior_days:
    for s, bars in dd.items():
        m: dict[int, float] = {}
        for b in bars:
            m.setdefault(hm(b.ts_ms), float(b.volume))
        vprof.setdefault(s, []).append(m)
say(f"prior recorder days: {[p.stem[8:] for p in prior_files[-20:]]}; pdh for {len(pdh)} symbols")

conn = sqlite3.connect("var/engine.db", timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
seen = {(r[0], r[1]) for r in conn.execute("SELECT symbol, strategy FROM signals WHERE trade_date=? AND book='A'", (D,))}
say(f"already stored today: {len(seen)}")


def prev_close():
    try:
        q = json.loads(Path("var/quotes_cache.json").read_text())
        return {x["symbol"]: x.get("prev_close") for x in q.get("quotes", []) if x.get("source") == "angel_ws"}
    except (OSError, json.JSONDecodeError):
        return {}


def scan():
    bars_by = load_day([WS / f"bars_1m_{DK}_backfill.jsonl", WS / f"bars_1m_{DK}.jsonl"])
    pc = prev_close()
    nb = bars_by.get("NIFTY 50", [])
    nb945 = [b for b in nb if hm(b.ts_ms) < 585]
    n945 = (nb945[-1].close / nb[0].open - 1) * 100 if nb945 else 0.0

    def ret_until(bs, minute):
        x = [b for b in bs if hm(b.ts_ms) < minute]
        return (x[-1].close / x[0].open - 1) * 100 if len(x) > 5 else None
    stocks = {k: v for k, v in bars_by.items() if k not in ("NIFTY 50", "NIFTY BANK", "INDIA VIX")}
    dec1015, _ = cross_sectional_ranks({k: x for k, bs in stocks.items() if (x := ret_until(bs, 615)) is not None})
    _, rank945 = cross_sectional_ranks({k: x - n945 for k, bs in stocks.items() if (x := ret_until(bs, 585)) is not None})
    new = []
    for sym, bars in stocks.items():
        if not bars or pc.get(sym) is None or hm(bars[0].ts_ms) > 556:
            continue   # every Book A rule needs the session from 09:15 (opening range, gap, VWAP, 09:45/10:15 ranks)
        mins = [hm(b.ts_ms) for b in bars]
        for st in STRATS:
            if (sym, st.id) in seen:
                continue
            tfm = timeframe_minutes(st.timeframe)
            done_b, cur, cur_start, span = [], [], None, tfm * 60_000
            for i in range(len(bars)):
                if tfm > 1:
                    start = (bars[i].ts_ms // span) * span
                    if cur_start is not None and start != cur_start:
                        done_b.append(_agg(cur_start, cur)); cur = []
                    cur_start = start; cur.append(bars[i])
                if (mins[i] - 555 + 1) % tfm != 0:
                    continue
                dec_ms = bars[i].ts_ms + 60_000
                if dec_ms >= SQ:
                    break
                ctx = build_intraday_context(trade_date=D, symbol=sym, prev_close=float(pc[sym]), pdh=pdh.get(sym),
                                             open_px=bars[0].open, decision_ms=dec_ms, prior_days_1m=None)
                slot = hm(dec_ms)
                vols = [m[slot] for m in vprof.get(sym, []) if slot in m]
                ctx.extras["slot_vol_avg"] = sum(vols) / len(vols) if vols else None
                ctx.extras["ret_decile"] = dec1015.get(sym) if slot >= 615 else None
                ctx.extras["rs_rank"] = rank945.get(sym) if slot >= 585 else None
                vb = done_b + [_agg(cur_start, cur)] if tfm > 1 else bars[: i + 1]
                try:
                    sigs = st.on_bar(sym, BarView(bars=vb, decision_ms=dec_ms, timeframe=st.timeframe), ctx)
                except Exception:  # noqa: BLE001
                    sigs = []
                if sigs:
                    s0 = sigs[0]
                    why = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in {**s0.features, **ctx.extras}.items()
                           if isinstance(v, (int, float)) and v is not None}
                    new.append(Signal(ts_ms=dec_ms, symbol=sym, side=s0.side, entry_ref=s0.entry_ref, stop=s0.stop, target=s0.target,
                                      time_exit_ms=s0.time_exit_ms, strategy=st.id, book="A", role="pick",
                                      features={**why, "decision": "shadow", "skip_reason": None, "source": "live_ws_stopgap"}))
                    seen.add((sym, st.id))
                    break
    if new:
        persist_signals(conn, new, D)
        for s in new:
            say(f"SIGNAL {datetime.fromtimestamp(s.ts_ms / 1000, IST):%H:%M} {s.symbol} {s.strategy} "
                f"{'BUY' if s.side > 0 else 'SELL'} @ {s.entry_ref:.2f} stop {s.stop:.2f}")
    return len(new), sum(len(v) for v in bars_by.values())


try:
    while True:
        n, nb = scan()
        say(f"scan: {nb} bars today, {n} new signals, {len(seen)} total")
        now = datetime.now(IST)
        if now.hour * 60 + now.minute >= 14 * 60 + 56:
            break
        time.sleep(60 - now.second + 2)
finally:
    conn.close()
    say("stopped")
