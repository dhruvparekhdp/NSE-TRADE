"""P0-2: settings defaults, env override, runtime override, live_orders forced false."""

from __future__ import annotations

from config.settings import get_setting, get_settings, reset_settings_cache, set_runtime_override


def test_defaults():
    s = get_settings()
    assert s.mode == "paper"
    assert s.live_orders is False
    assert s.capital_inr == 100_000.0
    assert s.min_position_inr == 100_000.0
    assert s.min_position_cnc_inr == 20_000.0
    assert s.books_enabled == ["A", "B"]
    assert s.strategies_enabled == []
    assert s.web_port == 8090
    assert s.web_host == "127.0.0.1"
    assert s.cookie_secure is True
    assert s.broker_squareoff_at == "15:10"
    assert s.square_off_at == "14:55"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CAPITAL_INR", "75000")
    monkeypatch.setenv("BOOKS_ENABLED", '["A"]')
    reset_settings_cache()
    s = get_settings()
    assert s.capital_inr == 75_000.0
    assert s.books_enabled == ["A"]


def test_runtime_override():
    set_runtime_override("kill_switch", True)
    assert get_setting("kill_switch") is True
    assert get_setting("capital_inr") == 100_000.0


def test_live_orders_forced_false_under_pytest(monkeypatch):
    monkeypatch.setenv("LIVE_ORDERS", "true")
    monkeypatch.setenv("NSE_FORCE_PAPER", "1")
    reset_settings_cache()
    s = get_settings()
    assert s.live_orders is False
