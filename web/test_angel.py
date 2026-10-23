"""POST /api/keys/test-angel — read-only Angel check (PLAN_V2 V0-6). Never places orders."""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web

from config.settings import get_settings
from web.angel_hints import hint_for
from web.auth import require_admin
from web.secure_channel import require_secure_channel

_RATE_WINDOW_S = 120.0
_last_call_mono: float = 0.0


def reset_rate_limit_for_tests() -> None:
    global _last_call_mono
    _last_call_mono = 0.0


def _mask_client(code: str) -> str:
    if len(code) <= 4:
        return "••••"
    return code[:2] + "•••" + code[-2:]


def run_test_angel(*, api: Any, totp_now: Any) -> dict[str, Any]:
    """Login → rmsLimit → allholding → position → logout. No tokens in the result."""
    from broker.angel import AngelBroker

    settings = get_settings()
    if not settings.angel_configured:
        return {
            "ok": False,
            "error_code": "NOT_CONFIGURED",
            "hint": "Save Angel API key, client code, MPIN and TOTP secret first",
            "client_code_masked": None,
        }
    code = settings.angel_client_code.get_secret_value() if settings.angel_client_code else ""
    pin = settings.angel_pin.get_secret_value() if settings.angel_pin else ""
    totp = totp_now() if callable(totp_now) else ""
    out: dict[str, Any] = {
        "ok": False,
        "client_code_masked": _mask_client(code),
        "available_cash": None,
        "holdings_count": 0,
        "holdings_value": 0.0,
        "positions_count": 0,
        "error_code": None,
        "hint": None,
    }
    try:
        # Soft-fail login so AB1050 etc. stay in the JSON (don't raise via AngelBroker._map_error)
        try:
            sess = api.generateSession(code, pin, totp)
        except Exception as exc:  # network
            out["error_code"] = "EXCEPTION"
            out["hint"] = hint_for(None, str(exc))
            return out
        if not sess.get("status"):
            code_e = str(sess.get("errorcode") or "")
            out["error_code"] = code_e or "LOGIN_FAILED"
            out["hint"] = hint_for(code_e, sess.get("message"))
            return out
        data = sess.get("data") or {}
        # keep tokens only on the broker object for subsequent calls — never in `out`
        broker = AngelBroker(api=api, totp_now=totp_now)
        broker.jwt = data.get("jwtToken")
        broker.refresh = data.get("refreshToken")
        broker.feed_token = data.get("feedToken")
        funds = broker.funds()
        fdata = funds.get("data") or {}
        cash = fdata.get("availablecash")
        try:
            out["available_cash"] = float(cash) if cash is not None else None
        except (TypeError, ValueError):
            out["available_cash"] = None
        holdings: list = []
        if hasattr(api, "allholding"):
            h = api.allholding()
            if isinstance(h, dict) and h.get("status"):
                raw = h.get("data")
                if isinstance(raw, dict):
                    holdings = raw.get("holdings") or []
                elif isinstance(raw, list):
                    holdings = raw
        out["holdings_count"] = len(holdings) if isinstance(holdings, list) else 0
        total = 0.0
        if isinstance(holdings, list):
            for row in holdings:
                if not isinstance(row, dict):
                    continue
                for k in ("productholdingvalue", "holdingvalue", "value"):
                    if row.get(k) is not None:
                        try:
                            total += float(row[k])
                        except (TypeError, ValueError):
                            pass
                        break
        out["holdings_value"] = total
        if hasattr(api, "position"):
            p = api.position()
            if isinstance(p, dict) and p.get("status"):
                rows = p.get("data") or []
                out["positions_count"] = len(rows) if isinstance(rows, list) else 0
        out["ok"] = True
        out["hint"] = "login ok — read-only checks passed"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        out["error_code"] = "EXCEPTION"
        out["hint"] = hint_for(None, msg)
        if "AB1050" in msg.upper():
            out["error_code"] = "AB1050"
            out["hint"] = hint_for("AB1050", msg)
    finally:
        try:
            if hasattr(api, "terminateSession") and code:
                api.terminateSession(code)
            elif hasattr(api, "logout"):
                api.logout()
        except Exception:  # noqa: BLE001
            pass
    # Never echo tokens
    for k in list(out):
        if "token" in k.lower() or "jwt" in k.lower():
            del out[k]
    return out


async def handle_test_angel(request: web.Request) -> web.Response:
    global _last_call_mono
    require_admin(request)
    require_secure_channel(request)
    now = time.monotonic()
    if now - _last_call_mono < _RATE_WINDOW_S:
        raise web.HTTPTooManyRequests(text="wait 2 minutes between Angel tests")
    _last_call_mono = now

    factory = request.app.get("angel_api_factory")
    totp_factory = request.app.get("angel_totp_factory")
    if factory is not None:
        api = factory()
        totp_now = totp_factory if totp_factory else (lambda: "000000")
    else:
        from broker.smartconnect_factory import build_smart_connect, totp_now_utc

        api = build_smart_connect()
        settings = get_settings()
        secret = settings.angel_totp_secret.get_secret_value() if settings.angel_totp_secret else ""

        def totp_now() -> str:
            return totp_now_utc(secret)

    body = run_test_angel(api=api, totp_now=totp_now)
    return web.json_response(body)
