"""JSON APIs for the multi-page portal (crypto-style hubs)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from aiohttp import web

from config.settings import get_setting, get_settings
from core.clock import Clock, session_state
from data.free_quotes import read_quotes_cache, refresh_default_universe
from web.auth import require_admin


async def handle_today(request: web.Request) -> web.Response:
    settings = get_settings()
    clock: Clock = request.app.get("clock", Clock())
    cache = read_quotes_cache(Path(settings.data_dir))
    age = None
    if cache.get("ts_ms"):
        age = max(0, int(time.time() * 1000) - int(cache["ts_ms"])) // 1000
    body: dict[str, Any] = {
        "mode": settings.mode,
        "live_orders": bool(get_setting("live_orders", settings.live_orders)),
        "kill_switch": bool(get_setting("kill_switch", settings.kill_switch)),
        "session_state": session_state(clock.now_ms()).value,
        "capital_inr": settings.capital_inr,
        "pnl_inr": 0.0,
        "costs_inr": 0.0,
        "positions": [],
        "orders": [],
        "quotes_age_s": age,
        "quotes_n": len(cache.get("quotes") or []),
        "data_source": "Yahoo chart API (free, delayed) — Angel reserved for orders",
        "angel_configured": settings.angel_configured,
    }
    return web.json_response(body)


async def handle_quotes(request: web.Request) -> web.Response:
    settings = get_settings()
    return web.json_response(read_quotes_cache(Path(settings.data_dir)))


async def handle_quotes_refresh(request: web.Request) -> web.Response:
    """Admin: pull free quotes now (yfinance)."""
    require_admin(request)
    settings = get_settings()
    payload = refresh_default_universe(Path(settings.data_dir), n=20)
    return web.json_response({"ok": True, "n": len(payload.get("quotes") or []), "ts_ms": payload["ts_ms"]})


async def handle_paper(request: web.Request) -> web.Response:
    """Paper book snapshot — empty-safe until paper fills are wired."""
    settings = get_settings()
    conn = request.app.get("db")
    open_rows: list[dict] = []
    closed_n = 0
    if conn is not None:
        try:
            open_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, symbol, book, strategy, side, qty, entry_price, stop_now, status "
                    "FROM trades WHERE status='open' LIMIT 50"
                ).fetchall()
            ]
            row = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed'").fetchone()
            closed_n = int(row["n"] or 0)
        except Exception:  # noqa: BLE001
            pass
    return web.json_response(
        {
            "mode": "paper",
            "capital_inr": settings.capital_inr,
            "open": open_rows,
            "closed_trades": closed_n,
            "note": "Paper fills use free quotes + cost model. Angel not required until live.",
        }
    )


async def handle_strategies(_request: web.Request) -> web.Response:
    from strategies.registry import ALL

    enabled = set(get_settings().strategies_enabled or [])
    rows = [
        {
            "id": s.id,
            "book": s.book,
            "timeframe": s.timeframe,
            "enabled": (not enabled) or (s.id in enabled),
        }
        for s in ALL.values()
    ]
    return web.json_response({"strategies": rows})


def _empty_opening(trade_date: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "phase": "overnight",
        "brief": None,
        "preopen": {"nifty": None, "snapshots_n": 0, "last_ms": None, "movers": []},
        "scorecard": None,
        "history": [],
    }


async def handle_opening(request: web.Request) -> web.Response:
    """Opening recorder payload (PLAN_V2 §7). Empty-safe until jobs fill tables."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    trade_date = request.rel_url.query.get("date") or datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    conn = request.app.get("db")
    body = _empty_opening(trade_date)
    if conn is None:
        return web.json_response(body)
    try:
        brief_row = conn.execute(
            "SELECT built_ms, json FROM morning_brief WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if brief_row:
            import json

            body["brief"] = json.loads(brief_row["json"])
            body["brief"]["built_ms"] = brief_row["built_ms"]
        snaps = conn.execute(
            "SELECT * FROM preopen_snapshots WHERE trade_date=? ORDER BY ts_ms", (trade_date,)
        ).fetchall()
        body["preopen"]["snapshots_n"] = len(snaps)
        if snaps:
            body["preopen"]["last_ms"] = int(snaps[-1]["ts_ms"])
            nifty = next((dict(s) for s in snaps if s["symbol"] == "NIFTY" and s["final"]), None)
            if nifty is None:
                nifty = next((dict(s) for s in snaps if s["symbol"] == "NIFTY"), None)
            if nifty:
                buy, sell = int(nifty.get("buy_qty") or 0), int(nifty.get("sell_qty") or 0)
                imb = (buy - sell) / (buy + sell) if (buy + sell) else None
                body["preopen"]["nifty"] = {
                    "iep": nifty.get("iep"),
                    "chg_pct": nifty.get("chg_pct"),
                    "imbalance": imb,
                }
        summary = conn.execute(
            "SELECT * FROM opening_summary WHERE trade_date=? AND symbol='NIFTY'", (trade_date,)
        ).fetchone()
        if summary:
            body["scorecard"] = {
                "nifty_gap_pct": summary["gap_pct"],
                "gap_filled_ms": summary["gap_filled_ms"],
                "or15": [summary["or15_low"], summary["or15_high"]],
                "breadth": None,
                "first5_vol_x": summary["first5_vol_x"],
                "open_type": summary["open_type"],
            }
        hist = conn.execute(
            "SELECT trade_date, gap_pct AS nifty_gap_pct, imbalance, open_type, open_to_close_pct "
            "FROM opening_summary WHERE symbol='NIFTY' ORDER BY trade_date DESC LIMIT 60"
        ).fetchall()
        body["history"] = [dict(r) for r in hist]
    except Exception:  # noqa: BLE001 — empty state on schema gaps
        pass
    return web.json_response(body)


async def handle_sentiment(request: web.Request) -> web.Response:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    trade_date = request.rel_url.query.get("date") or datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    conn = request.app.get("db")
    empty = {
        "composite": None,
        "label": "unknown",
        "parts": [],
        "markets": [],
        "risk_off_alarm": {"on": False, "since_ms": None, "reasons": []},
        "timeline": [],
    }
    if conn is None:
        return web.json_response(empty)
    try:
        import json

        row = conn.execute(
            "SELECT composite, parts_json, risk_off_alarm FROM sentiment_daily WHERE trade_date=?",
            (trade_date,),
        ).fetchone()
        if not row:
            return web.json_response(empty)
        composite = row["composite"]
        label = "neutral"
        if composite is not None:
            if composite >= 0.25:
                label = "risk_on"
            elif composite <= -0.25:
                label = "risk_off"
        return web.json_response(
            {
                "composite": composite,
                "label": label,
                "parts": json.loads(row["parts_json"] or "[]"),
                "markets": [],
                "risk_off_alarm": {
                    "on": bool(row["risk_off_alarm"]),
                    "since_ms": None,
                    "reasons": [],
                },
                "timeline": [],
            }
        )
    except Exception:  # noqa: BLE001
        return web.json_response(empty)


async def handle_headlines(request: web.Request) -> web.Response:
    hours = int(request.rel_url.query.get("hours") or 24)
    tag = request.rel_url.query.get("tag") or ""
    symbol = request.rel_url.query.get("symbol") or ""
    conn = request.app.get("db")
    empty: dict[str, Any] = {"rows": [], "tags": []}
    if conn is None:
        return web.json_response(empty)
    try:
        cutoff = int(time.time() * 1000) - hours * 3600 * 1000
        sql = (
            "SELECT ts_ms, source, title, link, event_type, symbol, score, "
            "nifty_move_next_60m FROM headlines WHERE ts_ms>=?"
        )
        args: list[Any] = [cutoff]
        if tag:
            sql += " AND event_type=?"
            args.append(tag)
        if symbol:
            sql += " AND symbol=?"
            args.append(symbol.upper())
        sql += " ORDER BY ts_ms DESC LIMIT 200"
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        tag_counts: dict[str, int] = {}
        for r in rows:
            et = r.get("event_type") or "other"
            tag_counts[et] = tag_counts.get(et, 0) + 1
        return web.json_response(
            {"rows": rows, "tags": [{"event_type": k, "n": v} for k, v in sorted(tag_counts.items())]}
        )
    except Exception:  # noqa: BLE001
        return web.json_response(empty)


def register_portal_routes(app: web.Application) -> None:
    app.router.add_get("/api/today", handle_today)
    app.router.add_get("/api/quotes", handle_quotes)
    app.router.add_post("/api/quotes/refresh", handle_quotes_refresh)
    app.router.add_get("/api/paper", handle_paper)
    app.router.add_get("/api/strategies", handle_strategies)
    app.router.add_get("/api/opening", handle_opening)
    app.router.add_get("/api/sentiment", handle_sentiment)
    app.router.add_get("/api/headlines", handle_headlines)
