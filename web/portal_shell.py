"""Serve the portal front end: the HTML shell, versioned static assets and the /nse/ base path.

WHY (PLAN_V2 V5-1, D7): the portal is a port of the crypto engine's micro-UI. It is published at
``/nse/`` behind nginx (or Tailscale), uses hash routing (``#/book/signals``) and loads every script
and style as ``portal/static/<name>?v=<hash>`` so the browser can cache them forever and still pick up
a new build the moment a file changes.

Only files that actually sit in ``web/portal/`` (and its ``hubs/`` folder) can be fetched, by exact
name, so a request can never walk out of that folder.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from aiohttp import web
from yarl import URL

PORTAL_DIR = Path(__file__).resolve().parent / "portal"
BASE_PATH = "/nse"                    # the public prefix; the server also answers without it
_TYPES = {".js": "application/javascript", ".css": "text/css"}
_PLACEHOLDER = re.compile(r"\{\{asset:([\w./-]+)\}\}")
_cache: dict[str, tuple[float, bytes, str]] = {}


def assets() -> dict[str, str]:
    """Whitelist: asset name -> content type (``hubs/book.js`` style names)."""
    found: dict[str, str] = {}
    for path in sorted(PORTAL_DIR.glob("*")) + sorted((PORTAL_DIR / "hubs").glob("*")):
        if path.suffix in _TYPES and path.is_file():
            found[path.relative_to(PORTAL_DIR).as_posix()] = _TYPES[path.suffix]
    return found


def read_asset(name: str) -> tuple[bytes, str]:
    """Bytes and a 10-hex-char content hash for one whitelisted asset (cached by mtime)."""
    path = PORTAL_DIR / name
    mtime = path.stat().st_mtime
    hit = _cache.get(name)
    if hit is None or hit[0] != mtime:
        body = path.read_bytes()
        hit = (mtime, body, hashlib.sha256(body).hexdigest()[:10])
        _cache[name] = hit
    return hit[1], hit[2]


def asset_url(name: str) -> str:
    return f"portal/static/{name}?v={read_asset(name)[1]}"


def render_shell() -> str:
    """portal.html with every ``{{asset:NAME}}`` replaced by its versioned URL."""
    html = (PORTAL_DIR / "portal.html").read_text(encoding="utf-8")
    html = _PLACEHOLDER.sub(lambda m: asset_url(m.group(1)), html)
    urls = {name: asset_url(name) for name in assets()}
    blob = json.dumps(urls).replace("</", "<\\/")
    return html.replace("{{assets_json}}", blob)


def head_snippet() -> str:
    """Chrome (shared header + skin) for server-rendered tool pages such as /keys."""
    return (
        f'<link rel="stylesheet" href="{asset_url("chrome.css")}">'
        f'<script src="{asset_url("nav.js")}"></script>'
        f'<script src="{asset_url("chrome.js")}" defer></script>'
    )


async def handle_shell(_request: web.Request) -> web.Response:
    return web.Response(text=render_shell(), content_type="text/html", headers={"Cache-Control": "no-cache"})


async def handle_base_redirect(_request: web.Request) -> web.Response:
    raise web.HTTPFound(BASE_PATH + "/")


async def handle_asset(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    kind = assets().get(name)
    if kind is None:
        raise web.HTTPNotFound()
    body, digest = read_asset(name)
    fresh = request.query.get("v") == digest
    cache = "public, max-age=31536000, immutable" if fresh else "no-cache"
    return web.Response(body=body, content_type=kind.split(";")[0], charset="utf-8", headers={"Cache-Control": cache})


async def handle_prefixed(request: web.Request) -> web.StreamResponse:
    """``/nse/<anything>`` is answered exactly like ``/<anything>`` (any method).

    nginx normally strips the prefix; this makes ``http://127.0.0.1:8090/nse/`` (and its POSTs, such as
    ``api/login``) work with no proxy, which is how the portal is developed and tested.
    """
    path = request.path[len(BASE_PATH):] or "/"
    clone = request.clone(rel_url=URL(path).with_query(request.rel_url.query_string))
    match = await request.app.router.resolve(clone)
    if match.http_exception is not None:
        raise match.http_exception
    match.add_app(request.app)
    match.freeze()
    clone._match_info = match  # same trick as aiohttp's normalize_path_middleware
    return await match.handler(clone)


async def handle_spa_fallback(request: web.Request) -> web.StreamResponse:
    """Unknown extension-less GETs return the shell (the router is client-side).

    API paths and file-like paths stay 404 so a typo in an endpoint is never answered with HTML.
    """
    path = request.path
    if path.startswith(("/api/", "/static/", "/portal/")) or "." in path.rsplit("/", 1)[-1]:
        raise web.HTTPNotFound()
    return await handle_shell(request)


def register_shell_routes(app: web.Application) -> None:
    """Register last: the catch-alls must come after every API and tool route."""
    app.router.add_get("/", handle_shell)
    app.router.add_get(BASE_PATH, handle_base_redirect)
    app.router.add_get("/portal/static/{name:[\\w./-]+}", handle_asset)
    app.router.add_route("*", BASE_PATH + "/{tail:.*}", handle_prefixed)
    app.router.add_get("/{tail:.*}", handle_spa_fallback)
