"""Refuse secret mutations over plain public HTTP (PLAN_V2 V0-2 / B24)."""

from __future__ import annotations

import ipaddress

from aiohttp import web


def peer_ip(request: web.Request) -> str:
    """Client IP: prefer X-Forwarded-For left-most when behind nginx, else remote."""
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.remote or ""


def _in_tailscale_cgnat(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr in ipaddress.ip_network("100.64.0.0/10")


def is_secure_channel(request: web.Request) -> bool:
    """True for HTTPS, localhost, or Tailscale CGNAT (100.64/10).

    Plain HTTP from a public IP must not receive key save/reveal/compare.
    """
    proto = (request.headers.get("X-Forwarded-Proto") or "").lower()
    if proto == "https":
        return True
    if request.secure:
        return True
    ip = peer_ip(request)
    if ip in {"127.0.0.1", "::1", "localhost"}:
        return True
    if _in_tailscale_cgnat(ip):
        return True
    return False


def require_secure_channel(request: web.Request) -> None:
    if not is_secure_channel(request):
        raise web.HTTPForbidden(text="secure channel required (HTTPS, localhost, or Tailscale)")
