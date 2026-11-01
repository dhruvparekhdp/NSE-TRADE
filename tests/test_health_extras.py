"""C16 health extras."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from engine.state import init_db
from web.portal_data import health_extras

IST = ZoneInfo("Asia/Kolkata")


def test_health_extras_fixture_fields(tmp_path, monkeypatch):
    data_dir = tmp_path / "var"
    ws = data_dir / "ws"
    ws.mkdir(parents=True)
    (data_dir / "quotes_cache.json").write_text("{}", encoding="utf-8")
    (ws / "bars_1m_20261030.jsonl").write_text('{"sym":"X","ts":"2026-10-30T09:05:00+05:30","c":1}\n')
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    from config.settings import reset_settings_cache

    reset_settings_cache()
    conn = init_db(data_dir / "e.db")
    conn.execute("INSERT INTO sessions(trade_date, login_ok) VALUES ('2026-10-30', 1)")
    conn.commit()
    now_ms = int(datetime(2026, 10, 30, 10, 0, tzinfo=IST).timestamp() * 1000)
    h = health_extras(conn, now_ms)
    assert h["last_login_ok"] is True
    assert h["recorder_bars_age_s"] is not None
    assert "market_filter" in h and "book_a_mode" in h
