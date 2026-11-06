"""Global test fixtures. live_orders must never be true under pytest (plan A15).

NSE-001: broker login and off-host sockets are refused for the whole session,
including when a developer shell or ``.env`` contains Angel keys.
"""

from __future__ import annotations

import os

import pytest

from tests.offline_guard import install

# Belt-and-braces: force paper even if a developer .env has live flags.
os.environ["NSE_FORCE_PAPER"] = "1"
os.environ["MODE"] = "paper"
os.environ["LIVE_ORDERS"] = "false"
# A shell DATABASE_URL must not make pytest open Postgres.
os.environ.pop("DATABASE_URL", None)
install()


@pytest.fixture(autouse=True)
def _reset_settings():
    from config.settings import get_settings, reset_settings_cache

    reset_settings_cache()
    s = get_settings()
    assert s.live_orders is False
    assert s.mode == "paper"
    yield
    reset_settings_cache()
