"""Refuse secret mutations over plain public HTTP (PLAN_V2 V0-2 / B24; review R3).

Trust proxy headers only when the TCP peer is loopback AND settings.trusted_proxy
is true (nginx on the same host). Spoofed X-Forwarded-* from a public client are ignored.
"""

from __future__ import annotations

import ipaddress

from aiohttp import web

from config.settings import get_settings


def _is_loopback(ip: str) -> bool:
    if ip in {"127.0.0.1", "::1", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _in_tailscale_cgnat(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr in ipaddress.ip_network("100.64.0.0/10")


def peer_ip(request: web.Request) -> str:
    """Client IP for audit / Tailscale checks.

    When behind a trusted local proxy: X-Real-IP (nginx) or the RIGHT-most
    X-Forwarded-For hop (the one nginx appended). Otherwise the TCP peer only.
    """
    remote = request.remote or ""
    settings = get_settings()
    if settings.trusted_proxy and _is_loopback(remote):
        xri = (request.headers.get("X-Real-IP") or "").strip()
        if xri:
            return xri
        xff = request.headers.get("X-Forwarded-For") or ""
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]  # right-most = closest to us / set by nginx
    return remote


def is_secure_channel(request: web.Request) -> bool:
    """True for direct HTTPS, direct localhost/Tailscale, or nginx TLS (trusted proxy).

    WHY (R3): never trust X-Forwarded-Proto / XFF from a public TCP peer — anyone can spoof them.
    """
    settings = get_settings()
    remote = request.remote or ""

    if settings.trusted_proxy and _is_loopback(remote):
        # Proxied: require explicit https scheme from nginx. Missing / http → insecure.
        proto = (request.headers.get("X-Forwarded-Proto") or "").lower()
        if proto == "https":
            return True
        if proto:
            return False
        # No X-Forwarded-Proto from the proxy → treat as insecure (forces nginx config).
        return False

    # Direct connection (or untrusted peer): ignore all forwarded headers.
    if request.secure:
        return True
    if _is_loopback(remote):
        return True
    if _in_tailscale_cgnat(remote):
        return True
    return False


def require_secure_channel(request: web.Request) -> None:
    if not is_secure_channel(request):
        raise web.HTTPForbidden(text="secure channel required (HTTPS, localhost, or Tailscale)")
