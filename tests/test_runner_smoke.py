"""P0-7: service starts without Angel keys; health says not configured."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import reset_settings_cache
from engine.runner import EngineRunner


@pytest.mark.asyncio
async def test_runner_health_not_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"DATA_DIR={tmp_path}\nMODE=paper\nLIVE_ORDERS=false\nSESSION_SECRET=test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"):
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()

    runner = EngineRunner()
    assert runner.settings.angel_configured is False

    server = TestServer(runner.app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.get("/api/health")
        data = await resp.json()
        assert data["status"] == "not configured"
        assert data["angel_configured"] is False
    finally:
        await client.close()
        runner.db.close()
