"""V0-8: mask / fingerprint / compare / reveal."""

from __future__ import annotations

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.key_display import fingerprint, first_diff_at, mask_value
from config.settings import reset_settings_cache
from web.app import create_app
from web.keys import reset_reveal_rate_for_tests


def test_mask_and_fingerprint_rules(monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "unit-master")
    assert mask_value("abcdefghij") == "ab•••ij"
    assert mask_value("1234", key="angel_pin") == "••••"
    assert mask_value("short") == "••••"
    assert fingerprint("abcdefghij") is not None
    assert len(fingerprint("abcdefghij") or "") == 12
    assert fingerprint("1234", key="angel_pin") is None
    assert fingerprint("shorty") is None  # under 8
    assert first_diff_at("abc", "abc") is None
    assert first_diff_at("abc", "axc") == 1


@pytest.mark.asyncio
async def test_compare_and_reveal(tmp_path, monkeypatch):
    reset_reveal_rate_for_tests()
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANGEL_API_KEY", "supersecretkey99")
    monkeypatch.setenv("SECRETS_MASTER_KEY", "unit-master")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    app = create_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        rows = (await (await client.get("/api/keys")).json())["rows"]
        angel = next(r for r in rows if r["key"] == "angel_api_key")
        assert angel["masked"].startswith("su")
        assert angel["fingerprint"]
        assert angel["length"] == len("supersecretkey99")

        ok = await (
            await client.post(
                "/api/keys/compare",
                json={"key": "angel_api_key", "value": "supersecretkey99"},
            )
        ).json()
        assert ok["match"] is True
        bad = await (
            await client.post(
                "/api/keys/compare",
                json={"key": "angel_api_key", "value": "supersecretkeyXX"},
            )
        ).json()
        assert bad["match"] is False
        assert bad["first_diff_at"] is not None

        # wrong password
        r = await client.post(
            "/api/keys/reveal",
            json={"key": "angel_api_key", "password": "nope"},
        )
        assert r.status == 403

        r = await client.post(
            "/api/keys/reveal",
            json={"key": "angel_api_key", "password": password},
        )
        assert r.status == 200
        assert r.headers.get("Cache-Control") == "no-store"
        body = await r.json()
        assert body["value"] == "supersecretkey99"

        # rate limit 5 / 10 min
        for _ in range(4):
            assert (
                await client.post(
                    "/api/keys/reveal",
                    json={"key": "angel_api_key", "password": password},
                )
            ).status == 200
        r = await client.post(
            "/api/keys/reveal",
            json={"key": "angel_api_key", "password": password},
        )
        assert r.status == 429
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_reveal_forbidden_over_plain_public_http(tmp_path, monkeypatch):
    reset_reveal_rate_for_tests()
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANGEL_API_KEY", "supersecretkey99")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    app = create_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        r = await client.post(
            "/api/keys/reveal",
            json={"key": "angel_api_key", "password": password},
            headers={"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "http"},
        )
        assert r.status == 403
    finally:
        await client.close()
