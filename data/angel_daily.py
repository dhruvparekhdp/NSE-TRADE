"""Fetch NSE ONE_DAY candles from Angel into the lake (V-FIX-2 F1a).

Angel prices are unadjusted; >35% one-day moves are flagged as likely corporate actions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from data.history import angel_candles_to_df
from data.lake import Lake

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
CORP_JUMP_PCT = 35.0
BACKFILL_SESSIONS = 320
MIN_SLEEP_S = 0.4
NIFTY_DAILY_SYMBOLS = ("NIFTYBEES", "NIFTY 50", "NIFTY")


class DailyCandleAPI(Protocol):
    def get_candle_data(self, payload: dict[str, Any]) -> list[list[Any]]: ...


def rows_to_daily_frame(rows: list[list[Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume", "source", "adj_factor"]
        )
    mins = angel_candles_to_df(rows, source="angel")
    mins["date"] = pd.to_datetime(mins["ts_ms"], unit="ms", utc=True).dt.tz_convert(IST).dt.strftime("%Y%m%d")
    mins["date"] = mins["date"].astype(int)
    mins["adj_factor"] = 1.0
    return mins[["date", "open", "high", "low", "close", "volume", "source", "adj_factor"]]


def detect_corp_jumps(
    daily: pd.DataFrame,
    symbol: str,
    *,
    threshold_pct: float = CORP_JUMP_PCT,
) -> list[dict[str, Any]]:
    """Flag likely splits/bonus on unadjusted Angel dailies."""
    if len(daily) < 2:
        return []
    out: list[dict[str, Any]] = []
    work = daily.sort_values("date")
    prev_close = None
    for _, row in work.iterrows():
        c = float(row["close"])
        if prev_close and prev_close > 0:
            chg = abs(c - prev_close) / prev_close * 100.0
            if chg >= threshold_pct:
                out.append(
                    {
                        "symbol": symbol.upper(),
                        "date": int(row["date"]),
                        "prev_close": prev_close,
                        "close": c,
                        "change_pct": round(chg, 2),
                    }
                )
        prev_close = c
    return out


def _date_window(end: date, sessions: int) -> tuple[str, str]:
    start = end - timedelta(days=int(sessions * 1.6) + 30)
    frm = datetime(start.year, start.month, start.day, 9, 15, tzinfo=IST).strftime("%Y-%m-%d %H:%M")
    to = datetime(end.year, end.month, end.day, 15, 30, tzinfo=IST).strftime("%Y-%m-%d %H:%M")
    return frm, to


def _fetch_with_backoff(api: DailyCandleAPI, payload: dict[str, Any], sleep_fn: Any) -> list[list[Any]]:
    last: list[list[Any]] = []
    for attempt in range(5):
        try:
            last = list(api.get_candle_data(payload))
            return last
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).upper()
            if "AB1021" in msg or "RATE" in msg:
                sleep_fn(MIN_SLEEP_S * (2**attempt) + 0.5)
                continue
            raise
    return last


def sync_symbol_daily(
    lake: Lake,
    conn: sqlite3.Connection | None,
    *,
    symbol: str,
    token: str,
    trade_date: date,
    api: DailyCandleAPI,
    sleep_fn: Any = None,
    backfill_sessions: int = BACKFILL_SESSIONS,
) -> dict[str, Any]:
    """Pull ONE_DAY history; backfill when the lake has fewer than backfill_sessions rows."""
    sleep_fn = sleep_fn or time.sleep
    existing = lake.read_daily(symbol)
    need = backfill_sessions if len(existing) < backfill_sessions else 1
    frm, to = _date_window(trade_date, need)
    payload = {
        "exchange": "NSE",
        "symboltoken": str(token),
        "interval": "ONE_DAY",
        "fromdate": frm,
        "todate": to,
    }
    rows = _fetch_with_backoff(api, payload, sleep_fn)
    sleep_fn(MIN_SLEEP_S)
    frame = rows_to_daily_frame(rows)
    if frame.empty:
        return {"symbol": symbol, "written": 0, "flags": []}
    written = lake.write_daily(symbol, frame)
    flags = detect_corp_jumps(frame, symbol)
    if conn is not None and flags:
        for f in flags:
            conn.execute(
                "INSERT INTO events(ts_ms, kind, json) VALUES (?,?,?)",
                (
                    int(datetime.now(tz=IST).timestamp() * 1000),
                    "corp_action_suspect",
                    json.dumps(f),
                ),
            )
        conn.commit()
    return {"symbol": symbol, "written": written, "flags": flags}


def job_daily_bars(
    lake: Lake,
    conn: sqlite3.Connection | None,
    *,
    symbols: list[tuple[str, str]],
    trade_date: date,
    api: DailyCandleAPI,
    sleep_s: float = MIN_SLEEP_S,
    backfill_sessions: int = BACKFILL_SESSIONS,
) -> dict[str, Any]:
    """16:10 IST job: refresh daily bars for universe + Nifty proxy symbols."""
    stats = {"symbols_ok": 0, "symbols_fail": 0, "corp_flags": 0, "trade_date": trade_date.isoformat()}
    for sym, tok in symbols:
        try:
            r = sync_symbol_daily(
                lake,
                conn,
                symbol=sym,
                token=tok,
                trade_date=trade_date,
                api=api,
                sleep_fn=time.sleep if sleep_s > 0 else (lambda _x: None),
                backfill_sessions=backfill_sessions,
            )
            stats["symbols_ok"] += 1
            stats["corp_flags"] += len(r.get("flags") or [])
        except Exception as exc:  # noqa: BLE001
            stats["symbols_fail"] += 1
            log.warning("daily_bars %s failed: %s", sym, exc)
        if sleep_s > 0:
            time.sleep(sleep_s)
    return stats


def universe_symbol_tokens(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Universe EQ names + Nifty daily proxy rows from instruments."""
    rows = conn.execute(
        "SELECT symbol, token FROM instruments WHERE in_universe=1 AND token IS NOT NULL AND token != ''"
    ).fetchall()
    out = [(str(r["symbol"]).upper(), str(r["token"])) for r in rows]
    have = {s for s, _ in out}
    for sym in NIFTY_DAILY_SYMBOLS:
        if sym in have:
            continue
        row = conn.execute(
            "SELECT symbol, token FROM instruments WHERE UPPER(symbol)=? AND token IS NOT NULL LIMIT 1",
            (sym.upper(),),
        ).fetchone()
        if row:
            out.append((str(row["symbol"]).upper(), str(row["token"])))
    return out
