"""V0-7: SmartConnect gets real X-ClientPublicIP / LocalIP / MAC headers."""

from __future__ import annotations

from types import SimpleNamespace

from broker.smartconnect_factory import apply_ip_headers
from config.settings import reset_settings_cache


def test_apply_ip_headers_sets_three_fields(monkeypatch):
    monkeypatch.setenv("EXPECTED_STATIC_IP", "203.0.113.10")
    reset_settings_cache()
    sess = SimpleNamespace(headers={})
    api = SimpleNamespace(_session=sess)
    headers = apply_ip_headers(api)
    assert headers["X-ClientPublicIP"] == "203.0.113.10"
    assert headers["X-ClientLocalIP"]
    assert headers["X-MACAddress"]
    assert sess.headers["X-ClientPublicIP"] == "203.0.113.10"
    assert "X-ClientLocalIP" in sess.headers
    assert "X-MACAddress" in sess.headers
