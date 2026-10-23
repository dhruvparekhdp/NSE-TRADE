"""aiohttp portal: health, login cookie, PAPER banner shell (plan A13 / P0-5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bcrypt
from aiohttp import web

from config.settings import get_setting, get_settings
from core.clock import Clock, session_state
from web.auth import (
    COOKIE_NAME,
    COOKIE_TTL_S,
    make_session_cookie,
    require_admin,
    session_hmac_secret,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Back-compat for keys/tests that import these names from web.app
_require_admin = require_admin


async def handle_health(request: web.Request) -> web.Response:
    from pathlib import Path

    from data.free_quotes import read_quotes_cache
    from web import portal_data

    settings = get_settings()
    clock: Clock = request.app.get("clock", Clock())
    now_ms = clock.now_ms()
    state = session_state(now_ms)
    conn = request.app.get("db")
    quotes = portal_data.build_quotes(read_quotes_cache(Path(settings.data_dir)))
    login = portal_data.one(conn, "SELECT login_ok FROM sessions ORDER BY trade_date DESC LIMIT 1")
    login_ok = bool(login and login["login_ok"])
    open_n = portal_data.one(conn, "SELECT COUNT(*) AS n FROM trades WHERE status='open'") or {}
    body: dict[str, Any] = {
        "ok": True,
        "mode": settings.mode,
        "live_orders": bool(get_setting("live_orders", settings.live_orders)),
        "kill_switch": bool(get_setting("kill_switch", settings.kill_switch)),
        "session_state": state.value,
        "login_ok": login_ok,
        "ws_connected": False,
        "last_tick_age_s": None,
        "open_positions": int(open_n.get("n") or 0),
        "angel_configured": settings.angel_configured,
        "configured": settings.angel_configured,
        "status": "ok" if settings.angel_configured else "not configured",
        # System > Health page (PLAN_V2 section 8)
        "jobs": portal_data.job_rows(conn, request.app.get("scheduler")),
        "memory_mb": portal_data.memory_mb(),
        "memory_limit_mb": 600,
        "sources": portal_data.source_rows(quotes, settings.angel_configured, login_ok, now_ms),
    }
    return web.json_response(body)


async def handle_login(request: web.Request) -> web.Response:
    settings = get_settings()
    try:
        data = await request.json()
    except json.JSONDecodeError as exc:
        raise web.HTTPBadRequest(text="invalid json") from exc
    password = data.get("password") or ""
    admin_hash = settings.portal_admin_hash
    plain = settings.admin_password.get_secret_value() if settings.admin_password else None
    ok = False
    if admin_hash:
        ok = bcrypt.checkpw(password.encode(), admin_hash.encode())
    elif plain:
        ok = password == plain
    if not (admin_hash or plain):
        raise web.HTTPServiceUnavailable(text="portal admin not configured")
    if not ok:
        raise web.HTTPUnauthorized(text="bad password")
    secret = session_hmac_secret()
    if not secret:
        raise web.HTTPServiceUnavailable(text="session secret not configured")
    cookie = make_session_cookie(secret)
    resp = web.json_response({"ok": True})
    # Path=/ so cookie works under nginx /nse/ prefix; Secure unless cookie_secure=false (V0-2)
    resp.set_cookie(
        COOKIE_NAME,
        cookie,
        httponly=True,
        samesite="Lax",
        max_age=COOKIE_TTL_S,
        path="/",
        secure=bool(settings.cookie_secure),
    )
    return resp


async def handle_kill(request: web.Request) -> web.Response:
    require_admin(request)
    data = await request.json()
    on = bool(data.get("on", True))
    conn = request.app.get("db")
    if conn is not None:
        from engine.state import set_setting

        set_setting(conn, "kill_switch", on, updated_by="portal")
    else:
        from config.settings import set_runtime_override

        set_runtime_override("kill_switch", on)
    return web.json_response({"ok": True, "kill_switch": on})


async def handle_books(request: web.Request) -> web.Response:
    conn = request.app.get("db")
    empty = {"A": {"trades": 0, "avg_r": 0.0}, "B": {"trades": 0, "avg_r": 0.0}}
    if conn is None:
        return web.json_response(empty)
    out = {}
    for book in ("A", "B"):
        row = conn.execute(
            "SELECT COUNT(*) AS n, AVG(r_mult) AS avg_r FROM trades WHERE book=? AND status='closed'",
            (book,),
        ).fetchone()
        out[book] = {"trades": int(row["n"] or 0), "avg_r": float(row["avg_r"] or 0.0)}
    return web.json_response(out)


def create_app(*, db: Any = None, clock: Clock | None = None) -> web.Application:
    app = web.Application()
    if db is not None:
        app["db"] = db
    app["clock"] = clock or Clock()
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/books", handle_books)
    app.router.add_post("/api/login", handle_login)
    app.router.add_post("/api/kill", handle_kill)
    from web.keys import register_keys_routes
    from web.portal_api import register_portal_routes
    from web.portal_shell import register_shell_routes

    register_keys_routes(app)
    register_portal_routes(app)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    register_shell_routes(app)  # last: holds the SPA catch-all
    return app
