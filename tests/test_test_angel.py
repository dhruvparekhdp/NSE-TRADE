"""V0-6: Test Angel read-only endpoint with fake SmartConnect."""

from __future__ import annotations

from typing import Any

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import reset_settings_cache
from web.app import create_app
from web.test_angel import reset_rate_limit_for_tests


class FakeSmartOK:
    def generateSession(self, code: str, pin: str, totp: str) -> dict[str, Any]:
        return {
            "status": True,
            "data": {"jwtToken": "SECRETJWT", "refreshToken": "SECRETREF", "feedToken": "FEED"},
        }

    def rmsLimit(self) -> dict[str, Any]:
        return {"status": True, "data": {"availablecash": "1234.50"}}

    def allholding(self) -> dict[str, Any]:
        return {
            "status": True,
            "data": {"holdings": [{"tradingsymbol": "SBIN-EQ", "holdingvalue": 500.0}]},
        }

    def position(self) -> dict[str, Any]:
        return {"status": True, "data": []}

    def terminateSession(self, code: str) -> dict[str, Any]:
        return {"status": True}


class FakeSmartAB1050:
    def generateSession(self, code: str, pin: str, totp: str) -> dict[str, Any]:
        return {"status": False, "errorcode": "AB1050", "message": "Invalid totp"}

    def terminateSession(self, code: str) -> dict[str, Any]:
        return {"status": True}


class FakeSmartNet:
    def generateSession(self, code: str, pin: str, totp: str) -> dict[str, Any]:
        raise ConnectionError("network down")


def _angel_env(monkeypatch, tmp_path) -> str:
    password = "test-admin"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "sess")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANGEL_API_KEY", "k")
    monkeypatch.setenv("ANGEL_CLIENT_CODE", "D1234")
    monkeypatch.setenv("ANGEL_PIN", "1234")
    monkeypatch.setenv("ANGEL_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    return password


@pytest.mark.asyncio
async def test_test_angel_ok(tmp_path, monkeypatch):
    reset_rate_limit_for_tests()
    password = _angel_env(monkeypatch, tmp_path)
    app = create_app()
    app["angel_api_factory"] = FakeSmartOK
    app["angel_totp_factory"] = lambda: "123456"
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        r = await client.post("/api/keys/test-angel", json={})
        assert r.status == 200
        body = await r.json()
        assert body["ok"] is True
        assert body["available_cash"] == 1234.50
        assert body["holdings_count"] == 1
        assert "SECRETJWT" not in str(body)
        assert body["client_code_masked"] == "D1•••34"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_test_angel_ab1050(tmp_path, monkeypatch):
    reset_rate_limit_for_tests()
    password = _angel_env(monkeypatch, tmp_path)
    app = create_app()
    app["angel_api_factory"] = FakeSmartAB1050
    app["angel_totp_factory"] = lambda: "000000"
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        r = await client.post("/api/keys/test-angel", json={})
        body = await r.json()
        assert body["ok"] is False
        assert body["error_code"] == "AB1050"
        assert "TOTP" in body["hint"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_test_angel_network_error(tmp_path, monkeypatch):
    reset_rate_limit_for_tests()
    password = _angel_env(monkeypatch, tmp_path)
    app = create_app()
    app["angel_api_factory"] = FakeSmartNet
    app["angel_totp_factory"] = lambda: "000000"
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        r = await client.post("/api/keys/test-angel", json={})
        body = await r.json()
        assert body["ok"] is False
        assert "network" in (body["hint"] or "").lower() or body["error_code"] == "EXCEPTION"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_test_angel_rate_limit(tmp_path, monkeypatch):
    reset_rate_limit_for_tests()
    password = _angel_env(monkeypatch, tmp_path)
    app = create_app()
    app["angel_api_factory"] = FakeSmartOK
    app["angel_totp_factory"] = lambda: "123456"
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post("/api/login", json={"password": password})).status == 200
        assert (await client.post("/api/keys/test-angel", json={})).status == 200
        r2 = await client.post("/api/keys/test-angel", json={})
        assert r2.status == 429
    finally:
        await client.close()
