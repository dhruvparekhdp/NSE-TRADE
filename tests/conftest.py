"""Global test fixtures. live_orders must never be true under pytest (plan A15)."""

from __future__ import annotations

import os

import pytest

# Belt-and-braces: force paper even if a developer .env has live flags.
os.environ["NSE_FORCE_PAPER"] = "1"
os.environ["MODE"] = "paper"
os.environ["LIVE_ORDERS"] = "false"


@pytest.fixture(autouse=True)
def _reset_settings():
    from config.settings import get_settings, reset_settings_cache

    reset_settings_cache()
    s = get_settings()
    assert s.live_orders is False
    assert s.mode == "paper"
    yield
    reset_settings_cache()
