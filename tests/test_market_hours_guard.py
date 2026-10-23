"""P0-8: deploy blocked Mon–Fri 09:00–15:45 IST unless force."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.market_hours_guard import deploy_blocked, main

IST = ZoneInfo("Asia/Kolkata")


def test_blocked_midday_weekday():
    now = datetime(2026, 10, 21, 11, 0, tzinfo=IST)  # Wed
    assert deploy_blocked(now) is True


def test_allowed_after_close():
    now = datetime(2026, 10, 21, 16, 0, tzinfo=IST)
    assert deploy_blocked(now) is False


def test_allowed_weekend():
    now = datetime(2026, 10, 24, 11, 0, tzinfo=IST)  # Sat
    assert deploy_blocked(now) is False


def test_force_bypasses():
    now = datetime(2026, 10, 21, 11, 0, tzinfo=IST)
    assert deploy_blocked(now, force=True) is False


def test_cli_exit_codes(monkeypatch):
    # Freeze "now" by patching datetime.now used inside — call deploy_blocked via main with force
    assert main(["--force", "true"]) == 0
