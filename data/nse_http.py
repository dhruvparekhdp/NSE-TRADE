"""Browser-like HTTP session for NSE website JSON (pre-open, FII/DII, index breadth).

WHY (MARKET_INDIA §8b, PLAN_V2 Q12): NSE's website JSON is unofficial and answers only requests that carry
the cookies of a normal page visit. We warm up on the home page once, then call the API with the same
cookie jar. It can break at any time, so every caller treats failure as "source unavailable" and stores a
stale flag instead of inventing numbers. Tests never import urllib here: they inject a fake `get_json`.
"""

from __future__ import annotations

import gzip
import http.cookiejar
import json
import time
import urllib.request
from collections.abc import Callable
from typing import Any

NSE_HOME = "https://www.nseindia.com/"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
}
_WARM_TTL_S = 240.0

JsonGetter = Callable[[str], Any]


class NseUnavailable(Exception):
    """NSE blocked the request, changed the shape, or the network failed."""


class NseSession:
    """Cookie-carrying session. Not thread-safe; one per job run is fine."""

    def __init__(self, *, timeout: float = 15.0) -> None:
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._timeout = timeout
        self._warmed_at: float | None = None  # None = never warmed (monotonic() starts at boot, so 0.0 is not "long ago")

    def _read(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with self._opener.open(req, timeout=self._timeout) as resp:  # noqa: S310 — fixed NSE hosts
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw

    def _warm(self) -> None:
        if self._warmed_at is not None and time.monotonic() - self._warmed_at < _WARM_TTL_S:
            return
        self._read(NSE_HOME)
        self._warmed_at = time.monotonic()

    def get_json(self, url: str) -> Any:
        try:
            self._warm()
            return json.loads(self._read(url).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — urllib/json/gzip all mean "unavailable"
            raise NseUnavailable(f"{type(exc).__name__}: {exc}") from exc
