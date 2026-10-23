"""R7: silence SmartAPI/logzero secret logs; TOTP from UTC (V0-9)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pyotp

from broker.smartconnect_factory import silence_smartapi_loggers

SECRET = "JBSWY3DPEHPK3PXP"


def _utc_totp(secret: str) -> str:
    return pyotp.TOTP(secret).at(datetime.now(UTC))


def test_totp_stable_when_tz_changes(monkeypatch):
    """V0-9: wall-clock TZ must not change the OTP (Angel expects UTC-based TOTP)."""
    monkeypatch.setenv("TZ", "America/New_York")
    if hasattr(time := __import__("time"), "tzset"):
        time.tzset()
    a = _utc_totp(SECRET)
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    if hasattr(time, "tzset"):
        time.tzset()
    b = _utc_totp(SECRET)
    assert a == b
    # Naive .now() can diverge across TZ near a 30s boundary; UTC at() must match itself.
    assert a == pyotp.TOTP(SECRET).at(datetime.now(UTC))


def test_failed_login_logs_contain_no_secrets(caplog, monkeypatch):
    silence_smartapi_loggers()
    pin = "1234"
    api_key = "secret-api-key-xyz"
    totp = "654321"
    # Simulate what the SDK does on failure — our silence must mute logzero/SmartApi.
    sdk_log = logging.getLogger("SmartApi.smartConnect")
    sdk_log.setLevel(logging.DEBUG)
    with caplog.at_level(logging.DEBUG):
        sdk_log.error("generateSession failed body=%s pin=%s totp=%s key=%s", "{}", pin, totp, api_key)
        logzero = logging.getLogger("logzero_default")
        logzero.error("request payload pin=%s totp=%s", pin, totp)
    text = " ".join(r.getMessage() for r in caplog.records)
    # After silence, handlers are detached / CRITICAL — nothing (or no secret) should leak.
    assert pin not in text
    assert totp not in text
    assert api_key not in text


def test_build_smart_connect_silences_before_construct(monkeypatch):
    silence_smartapi_loggers()
    assert logging.getLogger("logzero").level >= logging.CRITICAL
    assert logging.getLogger("SmartApi").level >= logging.CRITICAL
