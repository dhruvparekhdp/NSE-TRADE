"""Angel One SmartAPI wrapper (plan A8). Blocking SDK calls go through injectable runner.

REAL ORDERS go through broker.live_guard.assert_live_orders_allowed().
That needs LIVE_ORDERS_ENABLED and LIVE_ORDERS_CONFIRM, plus mode=live and live_orders.
Place/modify/cancel raise if any of those are off. This module does not call the SDK order methods.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from broker.errors import AuthError, RateLimited, Rejected, Unavailable
from broker.live_guard import assert_live_orders_allowed
from broker.live_guard import cancel_order as guarded_cancel
from broker.live_guard import modify_order as guarded_modify
from broker.live_guard import place_order as guarded_place
from config.settings import get_settings


class AngelBroker:
    def __init__(
        self,
        *,
        api: Any = None,
        totp_now: Callable[[], str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api = api
        self.totp_now = totp_now
        self.sleep = sleep
        self.jwt: str | None = None
        self.refresh: str | None = None
        self.feed_token: str | None = None
        self._last_order_ts = 0.0
        self.settings = get_settings()

    def _throttle(self) -> None:
        gap = 1.0 / max(1, int(self.settings.orders_per_second))
        now = time.monotonic()
        wait = gap - (now - self._last_order_ts)
        if wait > 0:
            self.sleep(wait)
        self._last_order_ts = time.monotonic()

    def _map_error(self, resp: dict[str, Any]) -> None:
        if resp.get("status") is True or resp.get("success") is True:
            return
        msg = str(resp.get("message") or resp.get("errorcode") or "unknown")
        code = str(resp.get("errorcode") or "")
        low = msg.lower()
        if "AB1021" in code or "too many" in low:
            raise RateLimited(msg)
        if "token" in low or "session" in low or "invalid" in low and "login" in low:
            raise AuthError(msg)
        if resp.get("status") is False:
            raise Rejected(msg)
        raise Unavailable(msg)

    def login(self) -> dict[str, Any]:
        assert self.api is not None
        settings = get_settings()
        code = settings.angel_client_code.get_secret_value() if settings.angel_client_code else ""
        pin = settings.angel_pin.get_secret_value() if settings.angel_pin else ""
        totp = self.totp_now() if self.totp_now else ""
        try:
            resp = self.api.generateSession(code, pin, totp)
        except Exception as exc:  # network
            raise Unavailable(str(exc)) from exc
        if not resp.get("status"):
            # one retry after 30s left to caller; map error
            self._map_error(resp)
        data = resp.get("data") or {}
        self.jwt = data.get("jwtToken")
        self.refresh = data.get("refreshToken")
        self.feed_token = data.get("feedToken")
        return resp

    def profile(self) -> dict[str, Any]:
        assert self.api is not None and self.refresh
        resp = self.api.getProfile(self.refresh)
        self._map_error(resp)
        return resp

    def funds(self) -> dict[str, Any]:
        assert self.api is not None
        resp = self.api.rmsLimit()
        self._map_error(resp)
        return resp

    def ltp(self, exchange: str, trading_symbol: str, token: str) -> dict[str, Any]:
        assert self.api is not None
        resp = self.api.ltpData(exchange, trading_symbol, token)
        self._map_error(resp)
        return resp

    def candles(self, payload: dict[str, Any]) -> list[list[Any]]:
        assert self.api is not None
        for attempt in range(5):
            try:
                resp = self.api.getCandleData(payload)
            except Exception as exc:
                raise Unavailable(str(exc)) from exc
            try:
                self._map_error(resp)
                return list(resp.get("data") or [])
            except RateLimited:
                self.sleep(2.0 * (attempt + 1))
        raise RateLimited("AB1021 retries exhausted")

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        assert_live_orders_allowed()
        self._throttle()
        assert self.api is not None
        resp = guarded_place(self.api, params)
        self._map_error(resp)
        return resp

    def modify_order(self, params: dict[str, Any]) -> dict[str, Any]:
        assert_live_orders_allowed()
        self._throttle()
        assert self.api is not None
        resp = guarded_modify(self.api, params)
        self._map_error(resp)
        return resp

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> dict[str, Any]:
        assert_live_orders_allowed()
        self._throttle()
        assert self.api is not None
        resp = guarded_cancel(self.api, order_id, variety)
        self._map_error(resp)
        return resp
