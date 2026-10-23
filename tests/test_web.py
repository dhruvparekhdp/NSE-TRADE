"""P0-5: health shape; POST without cookie → 401."""

from __future__ import annotations

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import reset_settings_cache
from web.app import create_app


@pytest.fixture
async def client(monkeypatch, tmp_path):
    password = "test-pass"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")  # TestClient speaks plain HTTP
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client, password
    await client.close()


async def test_health_shape(client):
    cli, _ = client
    resp = await cli.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    for key in (
        "ok",
        "mode",
        "live_orders",
        "kill_switch",
        "session_state",
        "login_ok",
        "ws_connected",
        "last_tick_age_s",
        "open_positions",
        "status",
    ):
        assert key in data
    assert data["mode"] == "paper"
    assert data["live_orders"] is False
    assert data["status"] == "not configured"


async def test_kill_requires_cookie(client):
    cli, _ = client
    resp = await cli.post("/api/kill", json={"on": True})
    assert resp.status == 401


async def test_login_then_kill(client):
    cli, password = client
    resp = await cli.post("/api/login", json={"password": password})
    assert resp.status == 200
    resp = await cli.post("/api/kill", json={"on": True})
    assert resp.status == 200
    body = await resp.json()
    assert body["kill_switch"] is True


async def test_index_shows_paper_banner(client):
    cli, _ = client
    resp = await cli.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "PAPER" in text
