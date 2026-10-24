"""Daily Angel login + instrument refresh for the runner (PLAN_V2 V-FIX-2 F1e/F1f, written by Claude 25 Oct 2026).

WHY: the 16:10 daily-bars job and the 16:20 scan need two things the runner never had: instrument tokens for the
Nifty 100 (from Angel's scrip master) and a logged-in Angel session. Both jobs were log-only stubs, so the paper
engine could not run in production.

Memory: the scrip master is ~35 MB of JSON. Loading it whole would cost a few hundred MB inside a 600 MB service
(PLAN A14), so rows are decoded one at a time and only NSE equities + the Nifty 50 index are kept.
TOTP: always from a UTC datetime (23 Oct incident: a TZ change mid-process produced a wrong first code).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
import time
import urllib.request
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
NIFTY_LIST = Path(__file__).resolve().parent.parent / "config" / "ind_nifty100list.csv"
INDEX_SYMBOL = "NIFTY 50"  # matches data.angel_daily.NIFTY_DAILY_SYMBOLS


def iter_json_array(text: str) -> Iterator[dict[str, Any]]:
    """Decode a top-level JSON array one object at a time (keeps peak memory near the raw text size)."""
    dec = json.JSONDecoder()
    i = text.index("[") + 1
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            return
        obj, i = dec.raw_decode(text, i)
        if isinstance(obj, dict):
            yield obj


def fetch_scrip_master_text(timeout: float = 90.0) -> str:
    req = urllib.request.Request(SCRIP_MASTER_URL, headers={"User-Agent": "nse-engine/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed Angel URL
        return resp.read().decode("utf-8")


def nifty100_rows(text: str | None = None) -> list[dict[str, str]]:
    raw = text if text is not None else NIFTY_LIST.read_text(encoding="utf-8")
    return [r for r in csv.DictReader(io.StringIO(raw)) if (r.get("Symbol") or "").strip()]


def _tick(raw: Any) -> float:
    """Scrip master tick_size is in paise ("5.000000" -> ₹0.05)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.05
    return round(v / 100.0, 4) if v >= 1 else v


def refresh_instruments(conn: sqlite3.Connection, scrip_text: str, nifty_csv: str | None = None) -> dict[str, Any]:
    """Upsert the Nifty 100 (+ Nifty 50 index) with Angel tokens; anything else leaves the universe."""
    want = {r["Symbol"].strip().upper(): r for r in nifty100_rows(nifty_csv)}
    found: dict[str, dict[str, Any]] = {}
    index_row: dict[str, Any] | None = None
    for r in iter_json_array(scrip_text):
        if str(r.get("exch_seg", "")).upper() != "NSE":
            continue
        sym = str(r.get("symbol", ""))
        if sym.endswith("-EQ") and sym[:-3].upper() in want:
            found[sym[:-3].upper()] = r
        elif index_row is None and str(r.get("name", "")).upper() in ("NIFTY", "NIFTY 50") and str(r.get("instrumenttype", "")).upper() == "AMXIDX":  # noqa: E501
            index_row = r
    now = int(time.time() * 1000)
    conn.execute("UPDATE instruments SET in_universe=0")
    for name, r in found.items():
        meta = want[name]
        conn.execute(
            "INSERT INTO instruments(symbol, token, trading_symbol, name, isin, tick_size, lot_size, in_universe, updated_ms) "  # noqa: E501
            "VALUES (?,?,?,?,?,?,?,1,?) ON CONFLICT(symbol) DO UPDATE SET token=excluded.token, trading_symbol=excluded.trading_symbol, "  # noqa: E501
            "name=excluded.name, isin=excluded.isin, tick_size=excluded.tick_size, lot_size=excluded.lot_size, in_universe=1, "  # noqa: E501
            "updated_ms=excluded.updated_ms",
            (name, str(r.get("token", "")), str(r.get("symbol", "")), meta.get("Company Name") or r.get("name"),
             meta.get("ISIN Code"), _tick(r.get("tick_size")), int(float(r.get("lotsize") or 1)), now),
        )
    if index_row is not None:
        conn.execute(
            "INSERT INTO instruments(symbol, token, trading_symbol, name, isin, tick_size, lot_size, in_universe, updated_ms) "  # noqa: E501
            "VALUES (?,?,?,?,NULL,0.05,1,0,?) ON CONFLICT(symbol) DO UPDATE SET token=excluded.token, updated_ms=excluded.updated_ms",  # noqa: E501
            (INDEX_SYMBOL, str(index_row.get("token", "")), str(index_row.get("symbol", "")), "Nifty 50", now),
        )
    conn.commit()
    missing = sorted(set(want) - set(found))
    return {"universe": len(found), "missing": missing, "index_token": bool(index_row)}


class AngelCandleClient:
    """Adapter: data.angel_daily expects get_candle_data(payload) -> rows; errors raise with Angel's code."""

    def __init__(self, api: Any) -> None:
        self.api = api

    def get_candle_data(self, payload: dict[str, Any]) -> list[list[Any]]:
        resp = self.api.getCandleData(payload) or {}
        if resp.get("status"):
            return list(resp.get("data") or [])
        raise RuntimeError(f"{resp.get('errorcode') or ''} {resp.get('message') or 'candle error'}".strip())


def angel_login(settings: Any, build_api: Any = None, totp_fn: Any = None) -> Any:
    """Log in with client code + MPIN + UTC TOTP. Returns the SmartConnect object or raises RuntimeError."""
    from broker.smartconnect_factory import build_smart_connect, totp_now_utc

    if not settings.angel_configured:
        raise RuntimeError("Angel keys not configured")
    api = (build_api or build_smart_connect)()
    secret = "".join(settings.angel_totp_secret.get_secret_value().split()).upper()
    code = settings.angel_client_code.get_secret_value().strip()
    pin = settings.angel_pin.get_secret_value().strip()
    resp = api.generateSession(code, pin, (totp_fn or totp_now_utc)(secret)) or {}
    if not resp.get("status"):
        raise RuntimeError(f"{resp.get('errorcode') or ''} {resp.get('message') or 'login failed'}".strip())
    return api


def record_session(conn: sqlite3.Connection, trade_date: date, ok: bool, error: str | None = None) -> None:
    conn.execute(
        "INSERT INTO sessions(trade_date, login_ok, login_ms, error) VALUES (?,?,?,?) ON CONFLICT(trade_date) DO UPDATE SET "  # noqa: E501
        "login_ok=excluded.login_ok, login_ms=excluded.login_ms, error=excluded.error",
        (trade_date.isoformat(), 1 if ok else 0, int(time.time() * 1000), None if ok else (error or "")[:200]),
    )
    conn.commit()
