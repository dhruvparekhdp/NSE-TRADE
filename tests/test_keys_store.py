"""Encrypted key store + /keys API (no network)."""

from __future__ import annotations

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.secret_box import is_sealed, open_, seal
from config.settings import reset_settings_cache
from web.app import create_app


def test_seal_roundtrip(monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "unit-test-master-key")
    sealed = seal("super-secret")
    assert is_sealed(sealed)
    assert open_(sealed) == "super-secret"


@pytest.mark.asyncio
async def test_keys_requires_login(tmp_path, monkeypatch):
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")  # TestClient speaks plain HTTP
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    app = create_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.get("/api/keys")
        assert r.status == 401
        r = await client.post("/api/login", json={"password": password})
        assert r.status == 200
        r = await client.get("/api/keys")
        assert r.status == 200
        data = await r.json()
        assert any(row["key"] == "angel_api_key" for row in data["rows"])
        r = await client.get("/keys")
        assert r.status == 200
        assert "KEYS" in await r.text()
    finally:
        await client.close()
