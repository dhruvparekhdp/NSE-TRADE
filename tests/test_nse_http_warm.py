"""NseSession warms the NSE cookie on first use even right after boot (monotonic() starts near 0)."""

from __future__ import annotations

from data import nse_http
from data.nse_http import NSE_HOME, NseSession


def test_first_warm_happens_soon_after_boot(monkeypatch):
    monkeypatch.setattr(nse_http.time, "monotonic", lambda: 5.0)
    s = NseSession()
    reads: list[str] = []
    monkeypatch.setattr(s, "_read", lambda url: reads.append(url) or b"")
    s._warm()
    assert reads == [NSE_HOME]
    s._warm()  # inside the TTL now: no second home-page read
    assert reads == [NSE_HOME]
