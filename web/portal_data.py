"""Builders for the portal's JSON endpoints (PLAN_V2 §7). Pure functions: no aiohttp here.

WHY: the portal front end is coded against the §7 shapes (``tests/fixtures/portal/*.json``). Every
builder returns the *whole* shape every time. When the table behind a field is missing or empty the
value is ``null`` / ``[]`` / ``0`` and the page shows an empty state: never a made-up number
(PLAN_V2 §8, AGENTS rule 6 spirit). Tables that later phases create (paper cycles, opening, flows,
headlines) are read defensively: if they are not there yet, the field stays empty.

All times are UTC epoch milliseconds; the browser shows IST (AGENTS rule 7).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from config.settings import get_setting, get_settings
from core.clock import IST, SessionState, session_state, to_ist
from data.calendar import Calendar, load_default_calendar
from web.reasons import reason_text

ROOT = Path(__file__).resolve().parent.parent

# Book B rules shown on the Paper book page (PLAN A10 / PLAN_V2 D1, V2-1). They are the design the
# engine is built to, not a reading from the engine: the page labels them "rules".
BOOK_B_RULES = {
    "timeframe": "1d",
    "stop": "2.5×ATR14 below entry",
    "trail": "highest close since entry − 2.5×ATR14, never lowered",
    "time_limit_sessions": 20,
}

# Go-live thresholds (PLAN A16-P4-4: "≥ 6 weeks and ≥ 100 trades per enabled strategy ... no
# unexplained parity faults for 2 weeks"). Proposed in V5, owner confirms (docs/phase-reports/V5.md).
GOLIVE_MIN_PAPER_WEEKS = 6
GOLIVE_MIN_TRADES = 100
GOLIVE_PARITY_DAYS = 14

SENTIMENT_LABEL_AT = 0.25  # |composite| at or above this is risk-on / risk-off; below is neutral

_COST_PARTS = ("brokerage", "stt", "exchange", "sebi", "stamp", "gst", "dp", "slippage")


# ---------------------------------------------------------------- sqlite helpers
def rows(conn: sqlite3.Connection | None, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a query; a missing table/column or no connection is an empty result, not an error."""
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []


def one(conn: sqlite3.Connection | None, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    got = rows(conn, sql, params)
    return got[0] if got else None


def has_table(conn: sqlite3.Connection | None, name: str) -> bool:
    return bool(one(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _hhmm_minus(hhmm: str, minutes: int) -> str:
    h, m = hhmm.split(":")
    total = int(h) * 60 + int(m) - int(minutes)
    return f"{total // 60:02d}:{total % 60:02d}"


# ---------------------------------------------------------------- session, calendar, meta
def _calendar() -> Calendar | None:
    try:
        return load_default_calendar()
    except (OSError, ValueError, KeyError):
        return None


def derived_times() -> dict[str, str | None]:
    """Engine square-off / no-entry derived from the broker's cut-off when the V1-3 settings exist."""
    broker = get_setting("broker_squareoff_at")
    lead = get_setting("squareoff_lead_min")
    if broker and lead is not None:
        entry_lead = int(get_setting("no_entry_lead_min", 20))
        square = _hhmm_minus(str(broker), int(lead))
        return {
            "broker_squareoff_at": str(broker),
            "squareoff_at": square,
            "no_entry_after": _hhmm_minus(square, entry_lead),
        }
    return {
        "broker_squareoff_at": None,
        "squareoff_at": str(get_setting("square_off_at", "15:05")),
        "no_entry_after": str(get_setting("no_entry_after", "14:45")),
    }


def _state_for(now_ms: int) -> SessionState:
    return session_state(
        now_ms,
        no_entry_after=str(get_setting("no_entry_after", "14:45")),
        square_off_at=str(get_setting("square_off_at", "15:05")),
    )


def _boundaries(d: date, cal: Calendar) -> list[tuple[str, str]]:
    special = cal.special_session(d)
    if special is not None:
        return [(special.open, "Muhurat session opens"), (special.close, "Muhurat session closes")]
    return [
        ("09:00", "pre-open starts"),
        ("09:15", "market opens"),
        (str(get_setting("no_entry_after", "14:45")), "no new entries"),
        (str(get_setting("square_off_at", "15:05")), "square-off"),
        ("15:30", "market closes"),
    ]


def next_change(now_ms: int, cal: Calendar | None) -> tuple[int | None, str | None]:
    """The next session boundary (ms, label) looking up to ten days ahead."""
    if cal is None:
        return None, None
    now = to_ist(now_ms)
    for offset in range(11):
        d = now.date() + timedelta(days=offset)
        if not cal.is_trading_day(d):
            continue
        for hhmm, label in _boundaries(d, cal):
            h, m = (int(x) for x in hhmm.split(":"))
            at = datetime(d.year, d.month, d.day, h, m, tzinfo=IST)
            if at > now:
                return int(at.timestamp() * 1000), label
    return None, None


_STATE_LABEL = {
    SessionState.PRE_OPEN: "Pre-open",
    SessionState.OPEN: "Market open",
    SessionState.NO_NEW_ENTRIES: "No new entries",
    SessionState.SQUARE_OFF: "Square-off",
    SessionState.CLOSED: "Closed",
    SessionState.HOLIDAY: "Holiday",
    SessionState.MUHURAT: "Muhurat session",
}


def session_block(now_ms: int) -> dict[str, Any]:
    cal = _calendar()
    state = _state_for(now_ms)
    label = _STATE_LABEL[state]
    if state == SessionState.HOLIDAY and cal is not None:
        name = cal.holiday_names.get(to_ist(now_ms).date())
        label = f"Holiday · {name}" if name else "Holiday"
    nxt_ms, nxt_label = next_change(now_ms, cal)
    return {
        "state": state.value,
        "stock_class": get_setting("stock_class"),  # V1-1 makes this per stock; None until then
        "label": label,
        "next_change_ms": nxt_ms,
        "next_label": nxt_label,
    }


def calendar_status(now_ms: int) -> tuple[bool, int | None]:
    """(calendar_ok, newest year with holiday data). Not OK when today's year has no file (V1-2)."""
    cal = _calendar()
    if cal is None:
        return False, None
    years = {d.year for d in cal.holidays} | {d.year for d in cal.special_sessions}
    if not years:
        return False, None
    return to_ist(now_ms).year in years, max(years)


def costs_verified() -> bool:
    try:
        raw = json.loads((ROOT / "config" / "costs_angel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    key = "verified_against_contract_note" if "verified_against_contract_note" in raw else "verified_against_calculator"
    return bool(raw.get(key, False))


def app_version() -> str:
    try:
        return str(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
    except (OSError, KeyError, ValueError):
        return "dev"


def build_meta(now_ms: int) -> dict[str, Any]:
    settings = get_settings()
    cal_ok, cal_year = calendar_status(now_ms)
    times = derived_times()
    return {
        "mode": settings.mode,
        "live_orders": bool(get_setting("live_orders", settings.live_orders)),
        "kill_switch": bool(get_setting("kill_switch", settings.kill_switch)),
        "book_a_mode": get_setting("book_a_mode", "shadow"),
        "market_filter": get_setting("market_filter", "off"),
        "session": session_block(now_ms),
        "calendar_ok": cal_ok,
        "calendar_year_loaded": cal_year,
        "costs_verified": costs_verified(),
        "capital_inr": float(get_setting("capital_inr", settings.capital_inr)),
        "squareoff_at": times["squareoff_at"],
        "no_entry_after": times["no_entry_after"],
        "broker_squareoff_at": times["broker_squareoff_at"],
        "version": app_version(),
    }


# ---------------------------------------------------------------- quotes, market
def build_quotes(cache: dict[str, Any]) -> dict[str, Any]:
    out = []
    for q in cache.get("quotes") or []:
        ltp, prev = _num(q.get("ltp")), _num(q.get("prev_close"))
        chg = (ltp - prev) / prev * 100.0 if ltp is not None and prev else None
        out.append(
            {"symbol": q.get("symbol"), "ltp": ltp, "prev_close": prev, "chg_pct": chg, "volume": q.get("volume")}
        )
    return {"ts_ms": cache.get("ts_ms") or None, "source": cache.get("source"), "quotes": out}


def _upcoming_calendar_events(now_ms: int, days: int = 30) -> list[dict[str, str]]:
    cal = _calendar()
    if cal is None:
        return []
    today = to_ist(now_ms).date()
    events = []
    for d in sorted(cal.holidays | set(cal.special_sessions)):
        if today <= d <= today + timedelta(days=days):
            special = cal.special_session(d)
            if special is not None:
                events.append(
                    {
                        "kind": "special_session",
                        "date": d.isoformat(),
                        "label": f"{special.name} {special.open}–{special.close}",
                    }
                )
            else:
                events.append(
                    {"kind": "holiday", "date": d.isoformat(), "label": cal.holiday_names.get(d) or "Exchange holiday"}
                )
    return events


_NIFTY_FILTERS: dict[str, Any] = {}  # {"day": iso, "vol_rank": x, "above_200dma": y}; recomputed once per IST day


def _nifty_filters(now_ms: int) -> tuple[float | None, bool | None]:
    """Vol rank (1y) and above-200-DMA from the daily lake, with the SAME functions the 16:20 scan uses
    (lab.market_filters), so the card and the scan's F1/F2 skips can never disagree. NIFTYBEES first, like
    engine.paper_jobs.nifty_closes; only sessions before today (today's bar is not final until the close)."""
    day = to_ist(now_ms).date()
    if _NIFTY_FILTERS.get("day") == day.isoformat():
        return _NIFTY_FILTERS["vol_rank"], _NIFTY_FILTERS["above_200dma"]
    from core.indicators import sma
    from data.lake import Lake
    from lab.market_filters import vol_rank_252

    rank = above = None
    try:
        root = Path(get_settings().data_dir) / "lake"
        if root.exists():
            cutoff = int(day.strftime("%Y%m%d"))
            for sym in ("NIFTYBEES", "NIFTY"):
                df = Lake(root).read_daily(sym)
                if df.empty:
                    continue
                dates = df["date"].astype(str).str.replace("-", "").str[:8].astype(int)
                closes = [float(c) for c in df.loc[dates < cutoff].sort_values("date")["close"]]
                if closes:
                    rank = vol_rank_252(closes)
                    s200 = sma(closes, 200)[-1] if len(closes) >= 200 else None
                    above = None if s200 is None else bool(closes[-1] >= s200)
                    break
    except Exception:  # noqa: BLE001 - a lake read problem must not break the Command page
        rank = above = None
    _NIFTY_FILTERS.update({"day": day.isoformat(), "vol_rank": rank, "above_200dma": above})
    return rank, above


def build_market(conn: sqlite3.Connection | None, quotes: dict[str, Any], now_ms: int) -> dict[str, Any]:
    nifty = next((q for q in quotes["quotes"] if str(q["symbol"]).upper() in {"NIFTY", "NIFTY50", "^NSEI"}), None)
    flows = one(conn, "SELECT * FROM flows ORDER BY trade_date DESC LIMIT 1") or {}
    cues = {
        r["key"]: r
        for r in rows(
            conn, "SELECT key, last, chg_pct, stale FROM global_cues WHERE ts_ms = (SELECT MAX(ts_ms) FROM global_cues)"
        )
    }
    gift = cues.get("GIFTNIFTY") or {}
    vol_rank, above_200 = _nifty_filters(now_ms)
    vix = cues.get("INDIAVIX") or {}
    return {
        "nifty": {"ltp": nifty["ltp"] if nifty else None, "chg_pct": nifty["chg_pct"] if nifty else None},
        "india_vix": _num(vix.get("last")),
        "nifty_vol_rank": vol_rank,
        "nifty_above_200dma": above_200,
        "fii_net_cr": _num(flows.get("fii_net_cr")),
        "dii_net_cr": _num(flows.get("dii_net_cr")),
        "gift_nifty_chg_pct": None if gift.get("stale") else _num(gift.get("chg_pct")),
        "next_events": _upcoming_calendar_events(now_ms),
    }


# ---------------------------------------------------------------- positions, swing, paper
def _trading_days_between(start: date, end: date, cal: Calendar | None) -> int:
    n, d = 0, start
    while d <= end:
        if cal is None or cal.is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def _marks(quotes: dict[str, Any]) -> dict[str, float]:
    return {q["symbol"]: q["ltp"] for q in quotes["quotes"] if q.get("ltp") is not None}


def position_row(t: dict[str, Any], marks: dict[str, float], now_ms: int, cal: Calendar | None) -> dict[str, Any]:
    side = -1 if t.get("side") == -1 else 1
    entry, qty = _num(t.get("entry_price")), int(t.get("qty") or 0)
    stop_init, stop_now = _num(t.get("stop_init")), _num(t.get("stop_now"))
    mark = marks.get(t["symbol"])
    risk = abs(entry - stop_init) if entry is not None and stop_init is not None else 0.0
    r_now = side * (mark - entry) / risk if mark is not None and entry is not None and risk > 0 else None
    unreal = side * (mark - entry) * qty if mark is not None and entry is not None else None
    entry_ms = t.get("entry_ms")
    held = t.get("sessions_held")
    if held is None and entry_ms:
        held = _trading_days_between(to_ist(entry_ms).date(), to_ist(now_ms).date(), cal)
    limit = BOOK_B_RULES["time_limit_sessions"]
    return {
        "trade_id": t["id"],
        "symbol": t["symbol"],
        "strategy": t.get("strategy"),
        "book": t.get("book"),
        "qty": qty,
        "entry": entry,
        "stop_init": stop_init,
        "stop_now": stop_now,
        "mark": mark,
        "r_now": r_now,
        "unrealised_inr": unreal,
        "sessions_held": held,
        "sessions_left": max(0, limit - held) if held is not None else None,
        "entry_ms": entry_ms,
    }


def closed_row(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_id": t["id"],
        "symbol": t["symbol"],
        "strategy": t.get("strategy"),
        "book": t.get("book"),
        "r": _num(t.get("r_mult")),
        "net_inr": _num(t.get("net_inr")),
        "costs_inr": _num(t.get("costs_inr")),
        "exit_reason": t.get("exit_reason"),
        "exit_text": reason_text(t.get("exit_reason")),
        "entry_ms": t.get("entry_ms"),
        "exit_ms": t.get("exit_ms"),
    }


def _closed_stats(conn: sqlite3.Connection | None, where: str = "", params: tuple = ()) -> dict[str, Any]:
    agg = (
        one(
            conn,
            "SELECT COUNT(*) AS n, SUM(CASE WHEN r_mult > 0 THEN 1 ELSE 0 END) AS wins, AVG(r_mult) AS avg_r, "
            f"SUM(r_mult) AS total_r FROM trades WHERE status='closed' {where}",
            params,
        )
        or {}
    )
    n = int(agg.get("n") or 0)
    return {
        "n": n,
        "win_rate": (agg.get("wins") or 0) / n * 100.0 if n else None,
        "avg_r": _num(agg.get("avg_r")) if n else None,
        "total_r": float(agg.get("total_r") or 0.0),
    }


def _takeskip(conn: sqlite3.Connection | None) -> dict[str, Any]:
    out = {}
    for name, decision in (("take", "taken"), ("skip", "skipped")):
        agg = one(
            conn,
            "SELECT COUNT(*) AS n, SUM(CASE WHEN virtual_status='running' THEN 1 ELSE 0 END) AS running, "
            "AVG(CASE WHEN virtual_status='resolved' THEN virtual_r END) AS avg_r "
            "FROM signals WHERE role='pick' AND book='B' AND decision=?",
            (decision,),
        )
        if agg is None:  # the V4 outcome columns are not there yet: count only
            agg = (
                one(
                    conn, "SELECT COUNT(*) AS n FROM signals WHERE role='pick' AND book='B' AND decision=?", (decision,)
                )
                or {}
            )
        out[name] = {
            "n": int(agg.get("n") or 0),
            "running": int(agg.get("running") or 0),
            "avg_r": _num(agg.get("avg_r")),
        }
    return out


def build_swing(conn: sqlite3.Connection | None, quotes: dict[str, Any], now_ms: int) -> dict[str, Any]:
    cal, marks = _calendar(), _marks(quotes)
    open_rows = rows(conn, "SELECT * FROM trades WHERE status='open' AND book='B' ORDER BY entry_ms")
    last = rows(conn, "SELECT * FROM trades WHERE status='closed' AND book='B' ORDER BY exit_ms DESC LIMIT 200")
    settings = get_settings()
    min_pos = get_setting("min_position_cnc_inr", settings.min_position_inr)
    return {
        "rules": {
            **BOOK_B_RULES,
            "risk_pct": float(get_setting("risk_per_trade_pct", settings.risk_per_trade_pct)),
            "min_position_inr": float(min_pos),
            "max_open": int(get_setting("max_open_swing", settings.max_open_swing)),
            "market_filter": get_setting("market_filter", "off"),
            "vol_rank_max": float(get_setting("market_filter_vol_rank_max", 0.667)),
            "excluded": list(get_setting("universe_excluded", []) or []),
        },
        "open": [position_row(t, marks, now_ms, cal) for t in open_rows],
        "closed": {**_closed_stats(conn, "AND book='B'"), "last": [closed_row(t) for t in last]},
        "takeskip": _takeskip(conn),
    }


def _empty_costs() -> dict[str, float | None]:
    return {k: 0.0 for k in _COST_PARTS}


def _sum_costs(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return _empty_costs()
    total = dict.fromkeys(_COST_PARTS, 0.0)
    for t in trades:
        try:
            parts = json.loads(t.get("costs_json") or "")
        except ValueError:
            return dict.fromkeys(_COST_PARTS)  # no breakdown stored: unknown, not zero
        for k in _COST_PARTS:
            total[k] += float(parts.get(k) or 0.0)
    return total


def _cycle(conn: sqlite3.Connection | None) -> dict[str, Any] | None:
    return one(conn, "SELECT * FROM paper_cycles ORDER BY id DESC LIMIT 1")


def build_paper(conn: sqlite3.Connection | None, quotes: dict[str, Any], now_ms: int) -> dict[str, Any]:
    cal, marks = _calendar(), _marks(quotes)
    cyc = _cycle(conn)
    open_rows = rows(conn, "SELECT * FROM trades WHERE status='open' ORDER BY entry_ms")
    positions = [position_row(t, marks, now_ms, cal) for t in open_rows]
    closed = rows(conn, "SELECT * FROM trades WHERE status='closed' ORDER BY exit_ms DESC")
    if cyc and "cycle_id" in (closed[0] if closed else {}):
        closed = [t for t in closed if t.get("cycle_id") == cyc["id"]]
    n = len(closed)
    net = sum(float(t.get("net_inr") or 0.0) for t in closed)
    wins = sum(1 for t in closed if (t.get("r_mult") or 0) > 0)
    unreal_known = [p["unrealised_inr"] for p in positions if p["unrealised_inr"] is not None]
    unreal = (
        sum(unreal_known) if positions and len(unreal_known) == len(positions) else (0.0 if not positions else None)
    )
    equity = None
    if cyc:  # wallet is the cash balance; held shares are valued at the last quote (or cost if unquoted)
        held = sum(p["qty"] * (p["mark"] if p["mark"] is not None else (p["entry"] or 0.0)) for p in positions)
        equity = float(cyc["wallet"]) + held
    return {
        "enabled": cyc is not None,
        "running": bool(cyc and cyc.get("status") == "running"),
        "cycle": {
            "id": cyc["id"] if cyc else None,
            "started_ms": cyc["started_ms"] if cyc else None,
            "starting_wallet": _num(cyc["starting_wallet"]) if cyc else None,
            "target_wallet": _num(cyc.get("target_wallet")) if cyc else None,
            "wallet": _num(cyc["wallet"]) if cyc else None,
            "peak_wallet": _num(cyc["peak_wallet"]) if cyc else None,
        },
        "equity": equity,
        "unrealised": unreal,
        "positions": positions,
        "summary": {
            "trades": n,
            "win_rate_pct": wins / n * 100.0 if n else None,
            "net_pnl": net,
            "expectancy_per_trade": net / n if n else None,
            "costs": _sum_costs(closed),
        },
        "history": [closed_row(t) for t in closed[:100]],
    }


# ---------------------------------------------------------------- signals
def build_signals(
    conn: sqlite3.Connection | None,
    now_ms: int,
    *,
    days: int = 14,
    book: str = "",
    strategy: str = "",
    role: str = "",
    decision: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    days, limit = max(1, min(int(days), 365)), max(1, min(int(limit), 2000))
    where, params = ["ts_ms >= ?"], [now_ms - days * 86_400_000]
    for col, val in (("book", book), ("strategy", strategy), ("role", role), ("decision", decision)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    found = rows(
        conn,
        f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY ts_ms DESC, id DESC LIMIT ?",
        (*params, limit),
    )
    min_pos = get_setting("min_position_cnc_inr", get_settings().min_position_inr)
    out, refused = [], {}
    for s in found:
        code = s.get("skip_reason") or ""
        text = reason_text(code, min_position_inr=min_pos)
        out.append(
            {
                "id": s["id"],
                "ts_ms": s["ts_ms"],
                "symbol": s["symbol"],
                "book": s["book"],
                "strategy": s["strategy"],
                "role": s["role"],
                "side": s["side"],
                "price": s.get("price"),
                "stop": s.get("stop"),
                "target": s.get("target"),
                "decision": s["decision"],
                "skip_reason": code or None,
                "reason_text": text,
                "virtual_status": s.get("virtual_status"),
                "virtual_r": _num(s.get("virtual_r")),
            }
        )
        if code and s["decision"] != "taken":
            bucket = refused.setdefault(code, {"reason": code, "reason_text": text, "n": 0})
            bucket["n"] += 1
    return {"rows": out, "refused": sorted(refused.values(), key=lambda r: -r["n"])}


# ---------------------------------------------------------------- lab, go-live, guard
def build_lab(conn: sqlite3.Connection | None) -> dict[str, Any]:
    from strategies.registry import ALL

    has_prereg = "prereg_id" in {r["name"] for r in rows(conn, "PRAGMA table_info(lab_trials)")}
    strategies = []
    for sid, strat in ALL.items():
        agg = one(conn, "SELECT COUNT(*) AS n, SUM(passed) AS passed FROM lab_trials WHERE strategy=?", (sid,)) or {}
        last = one(conn, "SELECT * FROM lab_trials WHERE strategy=? ORDER BY id DESC LIMIT 1", (sid,))
        strategies.append(
            {
                "id": sid,
                "book": strat.book,
                "last_report": None
                if last is None
                else {
                    "ts_ms": last["ts_ms"],
                    "period": last.get("period"),
                    "data_from": last.get("data_from"),
                    "data_to": last.get("data_to"),
                    "n": last.get("n"),
                    "avg_r": _num(last.get("avg_r")),
                    "win_pct": _num(last.get("win_pct")),
                    "passed": bool(last.get("passed")),
                    "post_hoc": bool(last.get("post_hoc")) if "post_hoc" in last else False,
                    "report_path": last.get("report_path"),
                },
                "trials": int(agg.get("n") or 0),
                "passed": int(agg.get("passed") or 0),
                "prereg_id": (last or {}).get("prereg_id") if has_prereg else None,
            }
        )
    total = (one(conn, "SELECT COUNT(*) AS n FROM lab_trials") or {}).get("n") or 0
    return {"trials_total": int(total), "strategies": strategies}


def gate(gid: str, label: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"id": gid, "label": label, "ok": bool(ok), "detail": detail}


def build_golive(conn: sqlite3.Connection | None, lake: dict[str, Any], now_ms: int) -> dict[str, Any]:
    """Server-side go-live gates (PLAN A16-P4-4 / P5, PLAN_V2 §8). The portal can never tick the last one."""
    settings = get_settings()
    cal_ok, cal_year = calendar_status(now_ms)
    cyc = _cycle(conn)
    weeks = (now_ms - cyc["started_ms"]) / (7 * 86_400_000) if cyc else 0.0
    passed = (one(conn, "SELECT COUNT(*) AS n FROM lab_trials WHERE passed=1") or {}).get("n") or 0
    per = rows(conn, "SELECT strategy, COUNT(*) AS n FROM trades WHERE status='closed' AND book='B' GROUP BY strategy")
    fewest = min((r["n"] for r in per), default=0)
    since = now_ms - GOLIVE_PARITY_DAYS * 86_400_000
    faults = [
        r
        for r in rows(conn, "SELECT trade_date, faults_json FROM parity")
        if r.get("faults_json") not in (None, "", "[]")
    ]
    recent = [r for r in faults if r["trade_date"] >= datetime.fromtimestamp(since / 1000, tz=IST).date().isoformat()]
    login = one(conn, "SELECT login_ok FROM sessions ORDER BY trade_date DESC LIMIT 1")
    gates = [
        gate(
            "real_data",
            "Research data is real, not synthetic",
            lake["symbols"] > 0 and lake["synthetic_files"] == 0,
            f"{lake['symbols']} symbols in the lake, {lake['synthetic_files']} synthetic"
            if lake["symbols"]
            else "no daily bars in the lake yet",
        ),
        gate("lab_gate", "At least one Book B trial passed the lab gate", passed > 0, f"{passed} passed trial(s)"),
        gate(
            "paper_weeks",
            f"Paper cycle has run {GOLIVE_MIN_PAPER_WEEKS}+ weeks",
            weeks >= GOLIVE_MIN_PAPER_WEEKS,
            f"{weeks:.1f} weeks" if cyc else "no paper cycle started",
        ),
        gate(
            "paper_trades",
            f"{GOLIVE_MIN_TRADES}+ closed paper trades per enabled strategy",
            fewest >= GOLIVE_MIN_TRADES,
            f"fewest per strategy: {fewest}",
        ),
        gate(
            "parity_clean",
            f"No parity faults in the last {GOLIVE_PARITY_DAYS} days",
            not recent and bool(cyc),
            f"{len(recent)} day(s) with faults" if cyc else "paper engine not running, nothing to compare",
        ),
        gate(
            "costs_verified",
            "Cost model checked against a real contract note",
            costs_verified(),
            "verified" if costs_verified() else "still the published rate card",
        ),
        gate(
            "calendar",
            "Holiday calendar covers this year",
            cal_ok,
            f"newest year loaded: {cal_year}" if cal_year else "no calendar loaded",
        ),
        gate(
            "angel_login",
            "Angel login works",
            bool(login and login["login_ok"]),
            "last login ok" if login and login["login_ok"] else "no successful login recorded",
        ),
        gate(
            "static_ip",
            "Registered static IP is configured",
            bool(settings.expected_static_ip),
            "set" if settings.expected_static_ip else "EXPECTED_STATIC_IP is empty",
        ),
        gate(
            "owner_yes",
            "Owner's written yes recorded in docs/DECISIONS.md",
            False,
            "this gate cannot be ticked from the portal: AGENTS rule 4",
        ),
    ]
    open_gates = [g for g in gates if not g["ok"]]
    return {"verdict": "NOT READY" if open_gates else "READY FOR OWNER REVIEW", "gates": gates}


def _flag(fid: str, on: bool, text: str) -> dict[str, Any]:
    return {"id": fid, "on": bool(on), "text": text}


def build_guard(conn: sqlite3.Connection | None, quotes: dict[str, Any], now_ms: int) -> dict[str, Any]:
    cal_ok, _ = calendar_status(now_ms)
    kill = bool(get_setting("kill_switch", get_settings().kill_switch))
    age = (now_ms - quotes["ts_ms"]) // 1000 if quotes["ts_ms"] else None
    pnl = (
        one(
            conn,
            "SELECT SUM(realized_inr) AS r, SUM(start_inr) AS s FROM daily_pnl WHERE trade_date=?",
            (to_ist(now_ms).date().isoformat(),),
        )
        or {}
    )
    loss_pct = (pnl["r"] / pnl["s"] * 100.0) if pnl.get("s") else None
    limit = float(get_setting("daily_loss_limit_pct", get_settings().daily_loss_limit_pct))
    cyc = _cycle(conn)
    floor_ok = None
    if cyc and cyc.get("starting_wallet"):
        floor_ok = (
            cyc["wallet"] >= cyc["starting_wallet"] * float(get_setting("floor_pct", get_settings().floor_pct)) / 100.0
        )
    faults = [
        {"trade_date": r["trade_date"], "book": r.get("book"), "faults": json.loads(r["faults_json"])}
        for r in rows(conn, "SELECT * FROM parity ORDER BY trade_date DESC LIMIT 30")
        if r.get("faults_json") not in (None, "", "[]")
    ]
    alarm = one(conn, "SELECT risk_off_alarm FROM sentiment_daily ORDER BY trade_date DESC LIMIT 1")
    quotes_stale = age is not None and age > 900
    flags = [
        _flag("kill_switch", kill, "Kill switch is ON: no new entries" if kill else "Kill switch is off"),
        _flag(
            "daily_loss",
            loss_pct is not None and loss_pct <= -limit,
            "Today's loss limit reached"
            if loss_pct is not None and loss_pct <= -limit
            else "Today's loss is inside the limit",
        ),
        _flag(
            "floor", floor_ok is False, "Wallet is at the floor" if floor_ok is False else "Wallet is above the floor"
        ),
        _flag("feed_stale", quotes_stale, "Quotes are stale" if quotes_stale else "Quotes are fresh or not needed"),
        _flag("reconcile", bool(faults), f"{len(faults)} day(s) with parity faults" if faults else "No parity faults"),
        _flag(
            "calendar",
            not cal_ok,
            "Holiday calendar missing for this year: trading jobs skip" if not cal_ok else "Holiday calendar loaded",
        ),
        _flag(
            "risk_off",
            bool(alarm and alarm["risk_off_alarm"]),
            "Risk-off alarm is active" if alarm and alarm["risk_off_alarm"] else "No risk-off alarm",
        ),
    ]
    return {
        "session": session_block(now_ms),
        "feed": {"last_tick_age_s": None, "stale": None, "quotes_age_s": age},
        "reconcile_faults": faults,
        "daily_loss_pct": loss_pct,
        "floor_ok": floor_ok,
        "kill_switch": kill,
        "flags": flags,
    }


# ---------------------------------------------------------------- data lake health
_lake_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _int_date(v: int) -> str:
    return f"{v // 10000:04d}-{(v // 100) % 100:02d}-{v % 100:02d}"


def scan_lake(root: Path, *, ttl_s: float = 60.0) -> dict[str, Any]:
    """Summarise ``bars_1d`` (cached for a minute: the page polls)."""
    key = str(root)
    hit = _lake_cache.get(key)
    if hit and time.time() - hit[0] < ttl_s:
        return hit[1]
    out: dict[str, Any] = {
        "symbols": 0,
        "first_date": None,
        "last_date": None,
        "missing_days": [],
        "missing_n": 0,
        "sources": {},
        "synthetic_files": 0,
        "has_adj_factor": False,
        "bhav_last_date": None,
    }
    daily_dir = root / "bars_1d"
    files = sorted(daily_dir.glob("*.parquet"))[:300] if daily_dir.is_dir() else []
    if files:
        try:
            import pandas as pd

            from data.health import trading_day_gaps

            best, firsts, lasts, bhav = None, [], [], []
            for f in files:
                cols = pd.read_parquet(f).columns
                df = pd.read_parquet(f, columns=[c for c in ("date", "source") if c in cols])
                if df.empty:
                    continue
                firsts.append(int(df["date"].min()))
                lasts.append(int(df["date"].max()))
                srcs = set(df["source"].astype(str)) if "source" in df else {"unknown"}
                for s in srcs:
                    out["sources"][s] = out["sources"].get(s, 0) + 1
                if srcs == {"synth"}:
                    out["synthetic_files"] += 1
                if "adj_factor" in cols:
                    out["has_adj_factor"] = True
                if "source" in df and (df["source"] == "bhav").any():
                    bhav.append(int(df.loc[df["source"] == "bhav", "date"].max()))
                if best is None or len(df) > len(best):
                    best = df
            out["symbols"] = len(firsts)
            if firsts:
                out["first_date"], out["last_date"] = _int_date(min(firsts)), _int_date(max(lasts))
                gaps = trading_day_gaps(best[["date"]], int(best["date"].min()), int(best["date"].max()))
                out["missing_n"] = len(gaps)
                out["missing_days"] = [_int_date(int(g)) for g in gaps[-30:]]
            if bhav:
                out["bhav_last_date"] = _int_date(max(bhav))
        except Exception:  # noqa: BLE001 - a broken parquet must not take the page down
            pass
    _lake_cache[key] = (time.time(), out)
    return out


def minutes_today(root: Path, now_ms: int) -> dict[str, Any]:
    base = root / "bars_1m"
    if not base.is_dir():
        return {"symbols": 0, "rows": 0}
    try:
        import pandas as pd

        d = to_ist(now_ms).date()
        lo = int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp() * 1000)
        syms = rows_n = 0
        for sym_dir in sorted(base.iterdir())[:120]:
            f = sym_dir / f"{d.year:04d}-{d.month:02d}.parquet"
            if not f.exists():
                continue
            ts = pd.read_parquet(f, columns=["ts_ms"])["ts_ms"]
            n = int(((ts >= lo) & (ts < lo + 86_400_000)).sum())
            if n:
                syms += 1
                rows_n += n
        return {"symbols": syms, "rows": rows_n}
    except Exception:  # noqa: BLE001
        return {"symbols": 0, "rows": 0}


def build_data_health(root: Path, now_ms: int) -> dict[str, Any]:
    lake = scan_lake(root)
    return {
        "lake": {
            k: lake[k]
            for k in ("symbols", "first_date", "last_date", "missing_days", "missing_n", "sources", "synthetic_files")
        },
        "bhav": {"last_date": lake["bhav_last_date"], "format": None},  # UDiFF/legacy flag arrives with V1-7
        "corp_actions_applied": lake["has_adj_factor"],
        "minutes_today": minutes_today(root, now_ms),
    }


# ---------------------------------------------------------------- opening, sentiment, headlines (V1b tables)
def _phase(now_ms: int) -> str:
    cal = _calendar()
    now = to_ist(now_ms)
    if cal is None or not cal.is_trading_day(now.date()):
        return "closed"
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60:
        return "overnight"
    if minutes < 9 * 60 + 15:
        return "preopen"
    if minutes < 9 * 60 + 45:
        return "opening"
    return "day" if minutes < 15 * 60 + 30 else "closed"


def _brief_skeleton() -> dict[str, Any]:
    return {
        "gift_nifty": {"chg_pct": None, "ts_ms": None},
        "us": [],
        "europe": [],
        "asia": [],
        "fx_commod": [],
        "fii_net_cr": None,
        "dii_net_cr": None,
        "india_vix": None,
        "top_headlines": [],
        "results_today": [],
        "events_today": [],
        "composite": None,
        "built_ms": None,
    }


def build_opening(conn: sqlite3.Connection | None, now_ms: int) -> dict[str, Any]:
    today = to_ist(now_ms).date().isoformat()
    brief = _brief_skeleton()
    row = one(conn, "SELECT built_ms, json FROM morning_brief WHERE trade_date=?", (today,))
    if row:
        try:
            brief.update({k: v for k, v in json.loads(row["json"]).items() if k in brief})
        except ValueError:
            pass
        brief["built_ms"] = row["built_ms"]
    pre = rows(
        conn,
        "SELECT * FROM preopen_snapshots WHERE trade_date=? "
        "AND ts_ms=(SELECT MAX(ts_ms) FROM preopen_snapshots WHERE trade_date=?)",
        (today, today),
    )
    nifty = next((r for r in pre if r["symbol"] == "NIFTY"), None)
    movers = sorted((r for r in pre if r["symbol"] != "NIFTY"), key=lambda r: -abs(r.get("chg_pct") or 0.0))[:10]

    def imbalance(r: dict[str, Any]) -> float | None:
        b, s = r.get("buy_qty"), r.get("sell_qty")
        return (b - s) / (b + s) if b is not None and s is not None and (b + s) else None

    snaps = (
        one(conn, "SELECT COUNT(DISTINCT ts_ms) AS n FROM preopen_snapshots WHERE trade_date=?", (today,)) or {}
    ).get("n") or 0
    summ = one(conn, "SELECT * FROM opening_summary WHERE trade_date=? AND symbol='NIFTY'", (today,)) or {}
    sent = one(conn, "SELECT breadth_adv, breadth_dec FROM sentiment_daily WHERE trade_date=?", (today,)) or {}
    hist = rows(
        conn,
        "SELECT trade_date, gap_pct, imbalance, open_type, open_to_close_pct FROM opening_summary "
        "WHERE symbol='NIFTY' ORDER BY trade_date DESC LIMIT 60",
    )
    return {
        "trade_date": today,
        "phase": _phase(now_ms),
        "brief": brief,
        "preopen": {
            "nifty": {
                "iep": nifty.get("iep") if nifty else None,
                "chg_pct": nifty.get("chg_pct") if nifty else None,
                "imbalance": imbalance(nifty) if nifty else None,
            },
            "snapshots_n": int(snaps),
            "last_ms": max((r["ts_ms"] for r in pre), default=None),
            "movers": [
                {"symbol": r["symbol"], "iep": r.get("iep"), "chg_pct": r.get("chg_pct"), "imbalance": imbalance(r)}
                for r in movers
            ],
        },
        "scorecard": {
            "nifty_gap_pct": summ.get("gap_pct"),
            "gap_filled_ms": summ.get("gap_filled_ms"),
            "or15": [summ.get("or15_low"), summ.get("or15_high")],
            "breadth": {"adv": sent.get("breadth_adv"), "dec": sent.get("breadth_dec")},
            "first5_vol_x": summ.get("first5_vol_x"),
            "open_type": summ.get("open_type"),
        },
        "history": [
            {
                "trade_date": r["trade_date"],
                "nifty_gap_pct": r["gap_pct"],
                "imbalance": r["imbalance"],
                "open_type": r["open_type"],
                "open_to_close_pct": r["open_to_close_pct"],
            }
            for r in hist
        ],
    }


def _label(composite: float | None) -> str | None:
    if composite is None:
        return None
    return (
        "risk-on" if composite >= SENTIMENT_LABEL_AT else "risk-off" if composite <= -SENTIMENT_LABEL_AT else "neutral"
    )


def build_sentiment(conn: sqlite3.Connection | None) -> dict[str, Any]:
    day = one(conn, "SELECT * FROM sentiment_daily ORDER BY trade_date DESC LIMIT 1")
    parts, composite = [], None
    if day:
        composite = day.get("composite")
        try:
            raw = json.loads(day["parts_json"])
        except ValueError:
            raw = []
        for p in raw if isinstance(raw, list) else []:
            parts.append(
                {
                    "key": p.get("key"),
                    "label": p.get("label") or p.get("key"),
                    "value": p.get("value"),
                    "weight": p.get("weight"),
                    "contribution": p.get("contribution"),
                    "ts_ms": p.get("ts_ms"),
                    "stale": bool(p.get("stale")),
                }
            )
    cues = rows(
        conn,
        "SELECT key, last, chg_pct, ts_ms, stale FROM global_cues WHERE ts_ms = (SELECT MAX(ts_ms) FROM global_cues)",
    )
    return {
        "composite": composite,
        "label": _label(composite),
        "parts": parts,
        "markets": [
            {
                "key": c["key"],
                "label": c["key"],
                "region": None,
                "last": c["last"],
                "chg_pct": c["chg_pct"],
                "ts_ms": c["ts_ms"],
                "stale": bool(c["stale"]),
            }
            for c in cues
        ],
        "risk_off_alarm": {"on": bool(day and day.get("risk_off_alarm")), "since_ms": None, "reasons": []},
        "timeline": [],
    }


def build_headlines(
    conn: sqlite3.Connection | None, now_ms: int, *, hours: int = 24, tag: str = "", symbol: str = ""
) -> dict[str, Any]:
    hours = max(1, min(int(hours), 24 * 14))
    where, params = ["ts_ms >= ?"], [now_ms - hours * 3_600_000]
    for col, val in (("event_type", tag), ("symbol", symbol)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    found = rows(
        conn, f"SELECT * FROM headlines WHERE {' AND '.join(where)} ORDER BY ts_ms DESC LIMIT 300", tuple(params)
    )
    tags = rows(
        conn,
        "SELECT event_type, COUNT(*) AS n FROM headlines WHERE ts_ms >= ? AND event_type IS NOT NULL "
        "GROUP BY event_type ORDER BY n DESC",
        (now_ms - hours * 3_600_000,),
    )
    return {
        "rows": [
            {
                "ts_ms": h["ts_ms"],
                "source": h.get("source"),
                "title": h["title"],
                "link": h.get("link"),
                "event_type": h.get("event_type"),
                "symbol": h.get("symbol"),
                "score": h.get("score"),
                "nifty_move_next_60m": h.get("nifty_move_next_60m"),
            }
            for h in found
        ],
        "tags": tags,
    }


# ---------------------------------------------------------------- events, tables
def build_events(conn: sqlite3.Connection | None, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    found = rows(conn, "SELECT id, ts_ms, kind, json FROM events ORDER BY id DESC LIMIT ?", (limit,))
    return {"rows": found}


_HIDDEN_TABLE_WORDS = ("secret", "key", "app_settings", "password", "token")


def build_tables(conn: sqlite3.Connection | None, limit: int = 20) -> dict[str, Any]:
    """Newest rows per table for System › Data (admin only). Anything that could hold a secret is skipped."""
    limit = max(1, min(int(limit), 200))
    out = {}
    for t in rows(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        name = t["name"]
        if any(w in name.lower() for w in _HIDDEN_TABLE_WORDS):
            continue
        n = (one(conn, f'SELECT COUNT(*) AS n FROM "{name}"') or {}).get("n") or 0
        out[name] = {
            "count": int(n),
            "rows": rows(conn, f'SELECT * FROM "{name}" ORDER BY rowid DESC LIMIT ?', (limit,)),
        }
    return {"tables": out}


# ---------------------------------------------------------------- health extras, universe, settings
def memory_mb() -> float | None:
    """Resident memory of this process in MB (AGENTS rule 10: stay under 600). None when unreadable."""
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    except Exception:  # noqa: BLE001
        return None


def source_rows(quotes: dict[str, Any], angel_configured: bool, login_ok: bool, now_ms: int) -> list[dict[str, Any]]:
    """Feed / source states for System > Health: what each source is, its age, whether it is working."""
    age = (now_ms - quotes["ts_ms"]) // 1000 if quotes["ts_ms"] else None
    return [
        {
            "id": "quotes",
            "label": "Quotes (Yahoo chart API, delayed)",
            "ok": bool(quotes["quotes"]) and (age is not None and age < 900),
            "age_s": age,
            "detail": f"{len(quotes['quotes'])} symbols" if quotes["quotes"] else "no quotes cached yet",
        },
        {
            "id": "angel",
            "label": "Angel One login",
            "ok": login_ok,
            "age_s": None,
            "detail": "logged in"
            if login_ok
            else ("keys saved, no login recorded" if angel_configured else "keys not saved"),
        },
    ]


def job_rows(conn: sqlite3.Connection | None, scheduler: Any) -> list[dict[str, Any]]:
    last = {}
    for r in rows(conn, "SELECT json, ts_ms FROM events WHERE kind='job_run' ORDER BY id DESC LIMIT 200"):
        try:
            j = json.loads(r["json"] or "{}")
        except ValueError:
            continue
        last.setdefault(j.get("job"), {"last_run_ms": r["ts_ms"], "last_ok": j.get("ok"), "result": j.get("result")})
    out = []
    for job in scheduler.get_jobs() if scheduler is not None else []:
        nxt = job.next_run_time
        info = last.get(job.id, {})
        out.append(
            {
                "id": job.id,
                "next_run_ms": int(nxt.timestamp() * 1000) if nxt else None,
                "last_run_ms": info.get("last_run_ms"),
                "last_ok": info.get("last_ok"),
                "result": info.get("result"),
            }
        )
    return out


# Runtime settings the Settings page may change. Never mode / live_orders (AGENTS rule 4) and never the
# market filter (it goes on only after the lab gate, PLAN_V2 D5). Each: (kind, low, high or choices).
SETTINGS_WHITELIST: dict[str, tuple[str, Any, Any]] = {
    "kill_switch": ("bool", None, None),
    "max_open_swing": ("int", 1, 10),
    "risk_per_trade_pct": ("float", 0.1, 1.0),
    "book_a_mode": ("choice", ("off", "shadow"), None),
}


def validate_setting(key: str, value: Any) -> Any:
    """Return the cleaned value or raise ValueError with a plain message."""
    if key not in SETTINGS_WHITELIST:
        raise ValueError("this setting cannot be changed from the portal")
    kind, lo, hi = SETTINGS_WHITELIST[key]
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if kind == "choice":
        if value not in lo:
            raise ValueError(f"must be one of {', '.join(lo)}")
        return value
    try:
        num = int(value) if kind == "int" else float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("must be a number") from exc
    if isinstance(value, bool) or not (lo <= num <= hi):
        raise ValueError(f"must be between {lo} and {hi}")
    return num


def build_settings(now_ms: int) -> dict[str, Any]:
    times = derived_times()
    items = []
    for key, (kind, lo, hi) in SETTINGS_WHITELIST.items():
        default = getattr(get_settings(), key, "shadow" if key == "book_a_mode" else None)
        items.append(
            {
                "key": key,
                "kind": kind,
                "value": get_setting(key, default),
                "min": lo if kind in ("int", "float") else None,
                "max": hi if kind in ("int", "float") else None,
                "choices": list(lo) if kind == "choice" else None,
            }
        )
    return {"settings": items, "derived": times, "session": session_block(now_ms)}


def build_universe(conn: sqlite3.Connection | None) -> dict[str, Any]:
    excluded = set(get_setting("universe_excluded", []) or [])
    found = rows(conn, "SELECT symbol, in_universe FROM instruments WHERE in_universe=1 ORDER BY symbol")
    return {
        "rows": [{"symbol": r["symbol"], "excluded": r["symbol"] in excluded} for r in found],
        "excluded": sorted(excluded),
    }
