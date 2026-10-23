"""V0-2 / R3: keys mutations need a real secure channel; proxy headers not spoofable."""

from __future__ import annotations

from unittest.mock import MagicMock

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from multidict import CIMultiDict

from config.settings import reset_settings_cache
from web.app import create_app
from web.secure_channel import is_secure_channel, peer_ip


def _req(*, remote: str = "", headers: dict | None = None, secure: bool = False):
    r = MagicMock()
    r.headers = CIMultiDict(headers or {})
    r.remote = remote
    r.secure = secure
    return r


def test_localhost_ok_without_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    reset_settings_cache()
    assert is_secure_channel(_req(remote="127.0.0.1")) is True


def test_tailscale_ok_direct(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    reset_settings_cache()
    assert is_secure_channel(_req(remote="100.64.1.20")) is True


def test_spoofed_https_from_public_ip_rejected(monkeypatch):
    """R3: public client cannot flip the gate with X-Forwarded-Proto."""
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    reset_settings_cache()
    assert (
        is_secure_channel(_req(remote="203.0.113.9", headers={"X-Forwarded-Proto": "https"}))
        is False
    )


def test_spoofed_xff_localhost_from_public_ip_rejected(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    reset_settings_cache()
    assert (
        is_secure_channel(
            _req(remote="203.0.113.9", headers={"X-Forwarded-For": "127.0.0.1"})
        )
        is False
    )


def test_nginx_https_trusted_proxy(monkeypatch):
    """remote=loopback + trusted_proxy + XFP https + X-Real-IP → secure."""
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    reset_settings_cache()
    req = _req(
        remote="127.0.0.1",
        headers={"X-Forwarded-Proto": "https", "X-Real-IP": "203.0.113.50"},
    )
    assert is_secure_channel(req) is True
    assert peer_ip(req) == "203.0.113.50"


def test_nginx_http_scheme_insecure(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    reset_settings_cache()
    assert (
        is_secure_channel(
            _req(
                remote="127.0.0.1",
                headers={"X-Forwarded-Proto": "http", "X-Real-IP": "203.0.113.50"},
            )
        )
        is False
    )


def test_trusted_proxy_missing_proto_insecure(monkeypatch):
    """Same-host nginx without X-Forwarded-Proto must not open the keys page."""
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    reset_settings_cache()
    assert is_secure_channel(_req(remote="127.0.0.1")) is False


def test_xff_uses_rightmost_when_proxied(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    reset_settings_cache()
    req = _req(
        remote="127.0.0.1",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "198.51.100.1, 203.0.113.9",
        },
    )
    assert peer_ip(req) == "203.0.113.9"


@pytest.mark.asyncio
async def test_keys_save_403_when_proxy_reports_http(tmp_path, monkeypatch):
    """nginx-style: peer is loopback but X-Forwarded-Proto is http → 403."""
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    app = create_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.post("/api/login", json={"password": password})
        assert r.status == 200
        r = await client.post(
            "/api/keys/save",
            json={"key": "angel_api_key", "value": "fake-key-value"},
            headers={
                "X-Real-IP": "203.0.113.50",
                "X-Forwarded-Proto": "http",
            },
        )
        assert r.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_login_cookie_has_secure_when_enabled(tmp_path, monkeypatch):
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    app = create_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.post("/api/login", json={"password": password})
        assert r.status == 200
        if hasattr(r.headers, "getall"):
            cookies = r.headers.getall("Set-Cookie")
        else:
            cookies = [r.headers.get("Set-Cookie", "")]
        assert "secure" in " ".join(cookies).lower()
    finally:
        await client.close()
