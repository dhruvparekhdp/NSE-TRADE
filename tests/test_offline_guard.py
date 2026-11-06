"""NSE-001: pytest must not log in to Angel or open an off-host socket (plan A15)."""

from __future__ import annotations

import socket

import pytest

from scripts.login_check import main as login_check_main
from tests.offline_guard import (
    OfflineBrokerError,
    OfflineSmartConnect,
    connection_allowed,
    refuse_offhost,
)


def test_only_loopback_is_allowed():
    assert connection_allowed(("127.0.0.1", 8090))
    assert connection_allowed(("localhost", 80))
    assert connection_allowed(("::1", 443))
    assert not connection_allowed(("1.1.1.1", 443))
    assert not connection_allowed(("apiconnect.angelone.in", 443))


def test_refuse_offhost_raises_before_any_connect():
    with pytest.raises(OSError, match="offline tests"):
        refuse_offhost(("8.8.8.8", 80))
    refuse_offhost(("127.0.0.1", 9))


def test_live_socket_refuses_public_hosts():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="offline tests"):
            sock.connect(("1.1.1.1", 443))
    finally:
        sock.close()


def test_smartconnect_is_the_offline_fake():
    from SmartApi import SmartConnect

    assert SmartConnect is OfflineSmartConnect
    api = SmartConnect(api_key="dummy")
    with pytest.raises(OfflineBrokerError):
        api.generateSession("DUMMY", "0000", "000000")
    with pytest.raises(OfflineBrokerError):
        api.placeOrder({})
    with pytest.raises(OfflineBrokerError):
        api.modifyOrder({})
    with pytest.raises(OfflineBrokerError):
        api.cancelOrder({})


def test_login_check_cannot_open_a_session(monkeypatch):
    monkeypatch.setenv("ANGEL_API_KEY", "dummy-key")
    monkeypatch.setenv("ANGEL_CLIENT_CODE", "DUMMY")
    monkeypatch.setenv("ANGEL_PIN", "0000")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "AAAAAAAAAAAAAAAA")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from config.settings import reset_settings_cache

    reset_settings_cache()
    with pytest.raises(OfflineBrokerError):
        login_check_main()
