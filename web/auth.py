"""Portal session cookies + admin gate (shared by app, keys, portal APIs)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from aiohttp import web

from config.settings import get_settings

COOKIE_NAME = "nse_session"
COOKIE_TTL_S = 12 * 3600


def session_hmac_secret() -> str:
    """Prefer SESSION_SECRET, else SECRETS_MASTER_KEY, else hash of ADMIN_PASSWORD.

    Must be identical for Set-Cookie and later verify — previously login derived
    from the typed password while /api/keys used empty settings.session_secret.
    """
    settings = get_settings()
    if settings.session_secret:
        return settings.session_secret.get_secret_value()
    master = os.environ.get("SECRETS_MASTER_KEY", "").strip()
    if master:
        return hashlib.sha256(f"nse-session-master:{master}".encode()).hexdigest()
    if settings.admin_password:
        pw = settings.admin_password.get_secret_value()
        return hashlib.sha256(f"nse-session:{pw}".encode()).hexdigest()
    if settings.portal_admin_hash:
        return hashlib.sha256(f"nse-session-hash:{settings.portal_admin_hash}".encode()).hexdigest()
    return ""


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_cookie(secret: str, subject: str = "admin") -> str:
    exp = int(time.time()) + COOKIE_TTL_S
    body = f"{subject}:{exp}"
    return f"{body}:{_sign(secret, body)}"


def verify_session_cookie(secret: str, cookie: str | None) -> bool:
    if not cookie or not secret:
        return False
    parts = cookie.split(":")
    if len(parts) != 3:
        return False
    subject, exp_s, sig = parts
    body = f"{subject}:{exp_s}"
    if not hmac.compare_digest(sig, _sign(secret, body)):
        return False
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    return exp >= int(time.time())


def require_admin(request: web.Request) -> None:
    """Raise 401 unless the portal session cookie verifies."""
    secret = session_hmac_secret()
    cookie = request.cookies.get(COOKIE_NAME)
    if not verify_session_cookie(secret, cookie):
        raise web.HTTPUnauthorized(text="login required")
