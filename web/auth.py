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
# Five wrong passwords, then 429 until the window expires. Stops a public brute force.
LOGIN_FAIL_WINDOW_S = 600.0
LOGIN_FAIL_MAX = 5

# Routes that change state or show secrets. Health and /api/login stay open.
_ADMIN_EXACT = frozenset(
    {
        "/api/kill",
        "/api/books",
        "/api/settings",
        "/api/tables",
        "/api/today",
        "/api/strategies",
        "/api/quotes/refresh",
        "/api/universe/exclude",
        "/keys",
    }
)


def bare_path(path: str) -> str:
    """Drop the /nse prefix nginx sometimes leaves on (portal shell clones these)."""
    path = path.split("?", 1)[0]
    if path == "/nse" or path.startswith("/nse/"):
        return path[len("/nse") :] or "/"
    return path


def is_admin_path(path: str) -> bool:
    """True when the path is an admin route and must not answer anonymously."""
    path = bare_path(path)
    if path in _ADMIN_EXACT:
        return True
    return path == "/api/keys" or path.startswith("/api/keys/")


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


def _const_eq(left: str, right: str) -> bool:
    """Compare two strings without leaking the length of the secret."""
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


def passwords_match(password: str) -> bool:
    """True when password matches the bcrypt hash or the plain ADMIN_PASSWORD.

    Plain compare is hashed first so a short passcode is not checked with ==.
    """
    settings = get_settings()
    if settings.portal_admin_hash:
        try:
            return bcrypt_check(password, settings.portal_admin_hash)
        except ValueError:
            return False
    plain = settings.admin_password.get_secret_value() if settings.admin_password else ""
    if not plain:
        return False
    return _const_eq(password, plain)


def bcrypt_check(password: str, hashed: str) -> bool:
    import bcrypt

    return bcrypt.checkpw(password.encode(), hashed.encode())


def admin_configured() -> bool:
    settings = get_settings()
    if settings.portal_admin_hash:
        return True
    return bool(settings.admin_password and settings.admin_password.get_secret_value())


def _bearer_ok(request: web.Request) -> bool:
    """True when Authorization matches ADMIN_TOKEN. Empty token never matches."""
    settings = get_settings()
    expected = settings.admin_token.get_secret_value() if settings.admin_token else ""
    if not expected:
        return False
    header = request.headers.get("Authorization") or ""
    presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
    return _const_eq(presented, expected)


def require_admin(request: web.Request) -> None:
    """Raise 401 unless the session cookie or the bearer token verifies."""
    if _bearer_ok(request):
        return
    secret = session_hmac_secret()
    cookie = request.cookies.get(COOKIE_NAME)
    if not verify_session_cookie(secret, cookie):
        raise web.HTTPUnauthorized(text="login required")


def login_rate_limited(request: web.Request) -> bool:
    """True after LOGIN_FAIL_MAX failures inside the window, for this process."""
    now = time.monotonic()
    recent = [t for t in request.app.get("login_failures", []) if now - t < LOGIN_FAIL_WINDOW_S]
    request.app["login_failures"] = recent
    return len(recent) >= LOGIN_FAIL_MAX


def note_login_failure(request: web.Request) -> None:
    now = time.monotonic()
    recent = [t for t in request.app.get("login_failures", []) if now - t < LOGIN_FAIL_WINDOW_S]
    recent.append(now)
    request.app["login_failures"] = recent


@web.middleware
async def admin_auth_middleware(request: web.Request, handler):
    """401 every admin route that a handler forgot to gate, including /nse/... clones."""
    if is_admin_path(request.path):
        require_admin(request)
    return await handler(request)
