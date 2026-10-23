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


def register_portal_routes(app: web.Application) -> None:
    app.router.add_get("/api/today", handle_today)
    app.router.add_get("/api/quotes", handle_quotes)
    app.router.add_post("/api/quotes/refresh", handle_quotes_refresh)
    app.router.add_get("/api/paper", handle_paper)
    app.router.add_get("/api/strategies", handle_strategies)
