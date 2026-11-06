"""Admin HTTP surface: localhost bind, and 401 without a session or token.

PLAN remote access: the portal must not answer admin calls on an open port.
"""

from __future__ import annotations

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import PublicBindRefused, get_settings, reset_settings_cache, resolve_bind_host
from web.app import create_app
from web.auth import is_admin_path

# State-changing or secret-bearing routes. Health and login stay open.
ADMIN_CALLS = [
    ("GET", "/api/books"),
    ("GET", "/api/today"),
    ("GET", "/api/strategies"),
    ("POST", "/api/kill"),
    ("GET", "/api/keys"),
    ("POST", "/api/keys/save"),
    ("POST", "/api/keys/clear"),
    ("POST", "/api/keys/compare"),
    ("POST", "/api/keys/reveal"),
    ("POST", "/api/keys/test-angel"),
    ("GET", "/keys"),
    ("GET", "/api/settings"),
    ("POST", "/api/settings"),
    ("GET", "/api/tables"),
    ("POST", "/api/quotes/refresh"),
    ("POST", "/api/universe/exclude"),
    ("GET", "/nse/api/books"),
    ("POST", "/nse/api/kill"),
    ("GET", "/nse/api/keys"),
]


def test_default_bind_is_localhost(monkeypatch):
    monkeypatch.delenv("WEB_HOST", raising=False)
    monkeypatch.delenv("EXPOSE_HTTP", raising=False)
    reset_settings_cache()
    settings = get_settings()
    assert settings.web_host == "127.0.0.1"
    assert settings.expose_http is False
    assert resolve_bind_host(settings) == "127.0.0.1"


def test_public_bind_refused_without_explicit_flag(monkeypatch):
    monkeypatch.setenv("WEB_HOST", "0.0.0.0")
    monkeypatch.delenv("EXPOSE_HTTP", raising=False)
    reset_settings_cache()
    with pytest.raises(PublicBindRefused):
        resolve_bind_host()


def test_public_bind_allowed_only_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("EXPOSE_HTTP", "true")
    reset_settings_cache()
    assert resolve_bind_host() == "0.0.0.0"


def test_loopback_names_do_not_need_the_flag(monkeypatch):
    monkeypatch.delenv("EXPOSE_HTTP", raising=False)
    for host in ("127.0.0.1", "localhost", "::1"):
        monkeypatch.setenv("WEB_HOST", host)
        reset_settings_cache()
        assert resolve_bind_host() == host


def test_admin_path_classifier_covers_the_locked_routes():
    for method, path in ADMIN_CALLS:
        assert is_admin_path(path), path
        assert method  # method is part of the call list the HTTP test uses
    assert is_admin_path("/api/health") is False
    assert is_admin_path("/api/login") is False
    assert is_admin_path("/") is False


@pytest.fixture
async def client(monkeypatch, tmp_path):
    password = "test-pass"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setenv("PORTAL_ADMIN_HASH", hashed)
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("ADMIN_TOKEN", "unit-test-admin-token")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    reset_settings_cache()
    app = create_app()
    http = TestClient(TestServer(app))
    await http.start_server()
    yield http, password
    await http.close()


@pytest.mark.parametrize("method,path", ADMIN_CALLS)
async def test_admin_routes_reject_anonymous(client, method, path):
    http, _password = client
    resp = await http.request(method, path, json={})
    assert resp.status == 401, path


async def test_health_stays_open_and_token_unlocks_admin(client):
    http, password = client
    health = await http.get("/api/health")
    assert health.status == 200
    denied = await http.post("/api/kill", json={"on": True})
    assert denied.status == 401
    authed = await http.post(
        "/api/kill",
        json={"on": False},
        headers={"Authorization": "Bearer unit-test-admin-token"},
    )
    assert authed.status == 200
    logged = await http.post("/api/login", json={"password": password})
    assert logged.status == 200
    again = await http.get("/api/books")
    assert again.status == 200


async def test_login_is_rate_limited(client):
    http, _password = client
    for _ in range(5):
        resp = await http.post("/api/login", json={"password": "wrong"})
        assert resp.status == 401
    blocked = await http.post("/api/login", json={"password": "wrong"})
    assert blocked.status == 429


async def test_plain_password_compare_rejects_wrong_lengths(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    monkeypatch.setenv("PORTAL_ADMIN_HASH", "")
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    app = create_app()
    http = TestClient(TestServer(app))
    await http.start_server()
    try:
        wrong = await http.post("/api/login", json={"password": "short-but-longer"})
        assert wrong.status == 401
        ok = await http.post("/api/login", json={"password": "short"})
        assert ok.status == 200
    finally:
        await http.close()
