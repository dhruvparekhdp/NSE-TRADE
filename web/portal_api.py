"""JSON APIs for the portal (PLAN_V2 §7). Thin aiohttp handlers over ``web/portal_data.py``.

WHY: the front end is built against these shapes before the engine fills the tables behind them, so
each handler returns the full shape with empty values when there is nothing to show. Reads are open
(the portal sits behind Tailscale / the admin gate); anything that changes state or shows secrets needs
the admin cookie, and writes also need a secure channel (V0-2).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from config.paths import lake_dir
from config.settings import get_setting, get_settings, set_runtime_override
from core.clock import Clock, session_state
from data.free_quotes import read_quotes_cache, refresh_default_universe
from web import portal_data as pd
from web.auth import require_admin
from web.secure_channel import require_secure_channel


def _conn(request: web.Request):
    return request.app.get("db")


def _now(request: web.Request) -> int:
    clock: Clock = request.app.get("clock", Clock())
    return clock.now_ms()


def _quotes(request: web.Request) -> dict[str, Any]:
    return pd.build_quotes(read_quotes_cache(Path(get_settings().data_dir)))


def _int_arg(request: web.Request, name: str, default: int) -> int:
    try:
        return int(request.query.get(name, default))
    except ValueError:
        return default


def _log_event(conn, kind: str, payload: dict[str, Any]) -> None:
    if conn is None:
        return
    conn.execute(
        "INSERT INTO events(ts_ms, kind, json) VALUES (?, ?, ?)", (int(time.time() * 1000), kind, json.dumps(payload))
    )
    conn.commit()


# ---------------------------------------------------------------- legacy (kept: the old pages and tests use them)
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
        "data_source": "Yahoo chart API (free, delayed): Angel reserved for orders",
        "angel_configured": settings.angel_configured,
    }
    return web.json_response(body)


async def handle_strategies(_request: web.Request) -> web.Response:
    from strategies.registry import ALL

    enabled = set(get_settings().strategies_enabled or [])
    rows = [
        {"id": s.id, "book": s.book, "timeframe": s.timeframe, "enabled": (not enabled) or (s.id in enabled)}
        for s in ALL.values()
    ]
    return web.json_response({"strategies": rows})


async def handle_quotes_refresh(request: web.Request) -> web.Response:
    """Admin: pull free quotes now (Yahoo chart API)."""
    require_admin(request)
    payload = refresh_default_universe(Path(get_settings().data_dir), n=20)
    return web.json_response({"ok": True, "n": len(payload.get("quotes") or []), "ts_ms": payload["ts_ms"]})


# ---------------------------------------------------------------- §7 endpoints
async def handle_meta(request: web.Request) -> web.Response:
    return web.json_response(pd.build_meta(_now(request)))


async def handle_quotes(request: web.Request) -> web.Response:
    return web.json_response(_quotes(request))


async def handle_market(request: web.Request) -> web.Response:
    return web.json_response(pd.build_market(_conn(request), _quotes(request), _now(request)))


async def handle_swing(request: web.Request) -> web.Response:
    return web.json_response(pd.build_swing(_conn(request), _quotes(request), _now(request)))


async def handle_paper(request: web.Request) -> web.Response:
    return web.json_response(pd.build_paper(_conn(request), _quotes(request), _now(request)))


async def handle_signals(request: web.Request) -> web.Response:
    q = request.query
    body = pd.build_signals(
        _conn(request),
        _now(request),
        days=_int_arg(request, "days", 14),
        book=q.get("book", ""),
        strategy=q.get("strategy", ""),
        role=q.get("role", ""),
        decision=q.get("decision", ""),
        limit=_int_arg(request, "limit", 500),
    )
    return web.json_response(body)


async def handle_lab(request: web.Request) -> web.Response:
    return web.json_response(pd.build_lab(_conn(request)))


async def handle_golive(request: web.Request) -> web.Response:
    lake = pd.scan_lake(lake_dir())
    return web.json_response(pd.build_golive(_conn(request), lake, _now(request)))


async def handle_guard(request: web.Request) -> web.Response:
    return web.json_response(pd.build_guard(_conn(request), _quotes(request), _now(request)))


async def handle_data_health(request: web.Request) -> web.Response:
    return web.json_response(pd.build_data_health(lake_dir(), _now(request)))


async def handle_opening(request: web.Request) -> web.Response:
    return web.json_response(pd.build_opening(_conn(request), _now(request)))


async def handle_sentiment(request: web.Request) -> web.Response:
    return web.json_response(pd.build_sentiment(_conn(request)))


async def handle_headlines(request: web.Request) -> web.Response:
    q = request.query
    body = pd.build_headlines(
        _conn(request),
        _now(request),
        hours=_int_arg(request, "hours", 24),
        tag=q.get("tag", ""),
        symbol=q.get("symbol", ""),
    )
    return web.json_response(body)


async def handle_events(request: web.Request) -> web.Response:
    return web.json_response(pd.build_events(_conn(request), _int_arg(request, "limit", 50)))


async def handle_tables(request: web.Request) -> web.Response:
    require_admin(request)
    return web.json_response(pd.build_tables(_conn(request), _int_arg(request, "limit", 20)))


# ---------------------------------------------------------------- Settings page (admin)
async def handle_settings_get(request: web.Request) -> web.Response:
    require_admin(request)
    return web.json_response(pd.build_settings(_now(request)))


async def handle_settings_set(request: web.Request) -> web.Response:
    """Change one whitelisted runtime setting; every change is logged (PLAN_V2 §8, Settings)."""
    require_admin(request)
    require_secure_channel(request)
    try:
        data = await request.json()
        key, value = data["key"], pd.validate_setting(data["key"], data.get("value"))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="expected {key, value}") from exc
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc
    conn = _conn(request)
    old = get_setting(key)
    if conn is not None:
        from engine.state import set_setting

        set_setting(conn, key, value, updated_by="portal")
    else:
        set_runtime_override(key, value)
    _log_event(conn, "setting_changed", {"key": key, "old": old, "new": value})
    return web.json_response({"ok": True, "key": key, "value": value})


async def handle_universe_get(request: web.Request) -> web.Response:
    return web.json_response(pd.build_universe(_conn(request)))


async def handle_universe_exclude(request: web.Request) -> web.Response:
    """Admin: exclude / include one symbol. The paper scanner reads this list from V4 on."""
    require_admin(request)
    require_secure_channel(request)
    try:
        data = await request.json()
        symbol, excluded = str(data["symbol"]).upper().strip(), bool(data["excluded"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise web.HTTPBadRequest(text="expected {symbol, excluded}") from exc
    if not symbol.isalnum() or len(symbol) > 20:
        raise web.HTTPBadRequest(text="bad symbol")
    current = set(get_setting("universe_excluded", []) or [])
    current = current | {symbol} if excluded else current - {symbol}
    conn, value = _conn(request), sorted(current)
    if conn is not None:
        from engine.state import set_setting

        set_setting(conn, "universe_excluded", value, updated_by="portal")
    else:
        set_runtime_override("universe_excluded", value)
    _log_event(conn, "universe_exclude", {"symbol": symbol, "excluded": excluded})
    return web.json_response({"ok": True, "excluded": value})


def register_portal_routes(app: web.Application) -> None:
    r = app.router
    r.add_get("/api/today", handle_today)
    r.add_get("/api/strategies", handle_strategies)
    r.add_post("/api/quotes/refresh", handle_quotes_refresh)
    r.add_get("/api/portal/meta", handle_meta)
    r.add_get("/api/quotes", handle_quotes)
    r.add_get("/api/market", handle_market)
    r.add_get("/api/swing", handle_swing)
    r.add_get("/api/paper", handle_paper)
    r.add_get("/api/portal/signals", handle_signals)
    r.add_get("/api/lab", handle_lab)
    r.add_get("/api/golive", handle_golive)
    r.add_get("/api/guard", handle_guard)
    r.add_get("/api/data-health", handle_data_health)
    r.add_get("/api/opening", handle_opening)
    r.add_get("/api/sentiment", handle_sentiment)
    r.add_get("/api/headlines", handle_headlines)
    r.add_get("/api/events", handle_events)
    r.add_get("/api/tables", handle_tables)
    r.add_get("/api/settings", handle_settings_get)
    r.add_post("/api/settings", handle_settings_set)
    r.add_get("/api/universe", handle_universe_get)
    r.add_post("/api/universe/exclude", handle_universe_exclude)
