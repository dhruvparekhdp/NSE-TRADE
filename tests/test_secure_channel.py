"""V0-2: keys mutations need HTTPS / localhost / Tailscale; cookie Secure flag."""

from __future__ import annotations

from unittest.mock import MagicMock

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer
from multidict import CIMultiDict

from config.settings import reset_settings_cache
from web.app import create_app
from web.secure_channel import is_secure_channel


def _req(*, remote: str = "", headers: dict | None = None, secure: bool = False):
    r = MagicMock()
    r.headers = CIMultiDict(headers or {})
    r.remote = remote
    r.secure = secure
    return r


def test_localhost_ok():
    assert is_secure_channel(_req(remote="127.0.0.1")) is True


def test_tailscale_ok():
    assert is_secure_channel(_req(remote="100.64.1.20")) is True


def test_https_forwarded_ok():
    assert (
        is_secure_channel(_req(remote="203.0.113.9", headers={"X-Forwarded-Proto": "https"}))
        is True
    )


def test_plain_http_public_forbidden():
    assert (
        is_secure_channel(_req(remote="203.0.113.9", headers={"X-Forwarded-Proto": "http"}))
        is False
    )


@pytest.mark.asyncio
async def test_keys_save_403_from_public_http(tmp_path, monkeypatch):
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")  # TestClient is http://
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
            headers={"X-Forwarded-For": "203.0.113.50", "X-Forwarded-Proto": "http"},
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
