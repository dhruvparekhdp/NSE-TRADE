"""Scheduled job bodies that write recorder / paper tables (PLAN_V2 V1b + V4; review R1).

Pure-ish helpers: runner calls these with the engine DB and injectable fetchers so tests
never hit the network.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from data.flows import refresh_flows
from data.global_cues import latest_cues, load_cue_specs, refresh_cues
from data.nse_http import JsonGetter, NseSession
from data.preopen import refresh_preopen
from engine.opening import brief_json, build_morning_brief, classify_opening
from engine.paper_engine import eod_fill_pending, resolve_outcomes, scan_book_b_day

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def _today_iso(now_ms: int | None = None) -> str:
    if now_ms is None:
        return datetime.now(IST).date().isoformat()
    return datetime.fromtimestamp(now_ms / 1000.0, tz=IST).date().isoformat()


def _now_ms() -> int:
    return int(datetime.now(IST).timestamp() * 1000)


def job_cues(conn: sqlite3.Connection, *, now_ms: int | None = None, fetch: Any = None) -> int:
    """Poll Yahoo cues every ~5 min; write global_cues."""
    ms = now_ms if now_ms is not None else _now_ms()
    kwargs: dict[str, Any] = {"now_ms": ms}
    if fetch is not None:
        kwargs["fetch"] = fetch
    return len(refresh_cues(conn, **kwargs))


def job_flows(conn: sqlite3.Connection, get_json: JsonGetter | None = None) -> bool:
    """FII/DII between 18:00–20:00 IST; write flows."""
    getter = get_json or NseSession().get_json
    return refresh_flows(conn, getter) is not None


def job_preopen(
    conn: sqlite3.Connection,
    *,
    now_ms: int | None = None,
    get_json: JsonGetter | None = None,
    final: bool = False,
) -> int:
    """NSE pre-open snapshots 09:00–09:15; write preopen_snapshots."""
    ms = now_ms if now_ms is not None else _now_ms()
    getter = get_json or NseSession().get_json
    snaps = refresh_preopen(
        conn,
        getter,
        trade_date=_today_iso(ms),
        ts_ms=ms,
        final=final,
    )
    return len(snaps)


def job_morning_brief(conn: sqlite3.Connection, *, now_ms: int | None = None) -> dict[str, Any]:
    """Freeze 08:45 brief into morning_brief (display only)."""
    ms = now_ms if now_ms is not None else _now_ms()
    trade_date = _today_iso(ms)
    cues_map = latest_cues(conn, now_ms=ms)
    specs = {s.key: s for s in load_cue_specs()}
    cue_rows = []
    for key, row in cues_map.items():
        spec = specs.get(key)
        cue_rows.append(
            {
                "key": key,
                "label": spec.label if spec else key,
                "region": spec.region if spec else "",
                "chg_pct": row.chg_pct,
                "ts_ms": row.ts_ms,
                "stale": row.stale,
            }
        )
    flow = conn.execute(
        "SELECT fii_net_cr, dii_net_cr FROM flows ORDER BY trade_date DESC LIMIT 1"
    ).fetchone()
    vix = cues_map.get("INDIAVIX") or cues_map.get("VIX")
    headlines = [
        dict(r)
        for r in conn.execute(
            "SELECT title, source, score, event_type FROM headlines ORDER BY ts_ms DESC LIMIT 10"
        )
    ]
    brief = build_morning_brief(
        trade_date=trade_date,
        built_ms=ms,
        cues=cue_rows,
        fii_net_cr=float(flow["fii_net_cr"]) if flow and flow["fii_net_cr"] is not None else None,
        dii_net_cr=float(flow["dii_net_cr"]) if flow and flow["dii_net_cr"] is not None else None,
        india_vix=float(vix.last) if vix and vix.last is not None else None,
        top_headlines=headlines,
        results_today=[],
        events_today=[],
        composite=None,
    )
    conn.execute(
        "INSERT OR REPLACE INTO morning_brief(trade_date, built_ms, json) VALUES (?,?,?)",
        (trade_date, ms, brief_json(brief)),
    )
    conn.commit()
    return brief


def job_opening_scorecard(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    symbol: str = "NIFTY",
    open_px: float,
    prev_close: float,
    last_px: float,
    imbalance: float | None = None,
    or15_high: float | None = None,
    or15_low: float | None = None,
    finalize_type: bool = False,
) -> None:
    """Write / update opening_summary; finalize open_type at 15:45."""
    gap_pct = (open_px - prev_close) / prev_close * 100.0 if prev_close else 0.0
    open_type = (
        classify_opening(gap_pct=gap_pct, open_px=open_px, close_px=last_px)
        if finalize_type
        else None
    )
    conn.execute(
        "INSERT INTO opening_summary(trade_date, symbol, open, prev_close, gap_pct, imbalance, "
        "or15_high, or15_low, close, open_to_close_pct, open_type) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(trade_date, symbol) DO UPDATE SET "
        "open=excluded.open, prev_close=excluded.prev_close, gap_pct=excluded.gap_pct, "
        "imbalance=COALESCE(excluded.imbalance, opening_summary.imbalance), "
        "or15_high=COALESCE(excluded.or15_high, opening_summary.or15_high), "
        "or15_low=COALESCE(excluded.or15_low, opening_summary.or15_low), "
        "close=excluded.close, open_to_close_pct=excluded.open_to_close_pct, "
        "open_type=COALESCE(excluded.open_type, opening_summary.open_type)",
        (
            trade_date,
            symbol,
            open_px,
            prev_close,
            gap_pct,
            imbalance,
            or15_high,
            or15_low,
            last_px,
            (last_px - open_px) / open_px * 100.0 if open_px else None,
            open_type,
        ),
    )
    conn.commit()


def persist_signals(conn: sqlite3.Connection, signals: list[Any], trade_date: str) -> None:
    import json

    for sig in signals:
        conn.execute(
            "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, "
            "target, features_json, decision, skip_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sig.ts_ms,
                trade_date,
                sig.symbol,
                sig.book,
                sig.strategy,
                sig.side,
                sig.role,
                sig.entry_ref,
                sig.stop,
                sig.target,
                json.dumps(sig.features or {}),
                (sig.features or {}).get("decision", "taken" if sig.role == "pick" else sig.role),
                (sig.features or {}).get("skip_reason"),
            ),
        )
    conn.commit()


def persist_pending(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    symbol: str,
    strategy: str,
    side: int,
    qty: int,
    limit_price: float,
    stop: float | None,
    target: float | None,
    created_ms: int,
) -> None:
    conn.execute(
        "INSERT INTO pending_orders(trade_date, symbol, book, strategy, side, qty, limit_price, "
        "stop, target, status, created_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (trade_date, symbol, "B", strategy, side, qty, limit_price, stop, target, "pending", created_ms),
    )
    conn.commit()


def load_pending_signals(conn: sqlite3.Connection, trade_date: str) -> list[Any]:
    from core.types import Signal

    rows = conn.execute(
        "SELECT * FROM pending_orders WHERE trade_date=? AND status='pending'", (trade_date,)
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            Signal(
                ts_ms=int(r["created_ms"]),
                symbol=r["symbol"],
                side=int(r["side"]),
                entry_ref=float(r["limit_price"]),
                stop=float(r["stop"] or r["limit_price"]),
                target=r["target"],
                time_exit_ms=None,
                strategy=r["strategy"],
                book="B",
                role="pick",
                features={"pending_id": r["id"]},
            )
        )
    return out


__all__ = [
    "job_cues",
    "job_flows",
    "job_preopen",
    "job_morning_brief",
    "job_opening_scorecard",
    "persist_signals",
    "persist_pending",
    "load_pending_signals",
    "eod_fill_pending",
    "resolve_outcomes",
    "scan_book_b_day",
]
