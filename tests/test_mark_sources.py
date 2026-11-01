"""C19: mark chain quote → 1m recorder → daily lake."""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from data.lake import Lake
from data.mark_sources import resolve_mark
from web.portal_data import build_paper

IST = ZoneInfo("Asia/Kolkata")


def test_bar_1m_when_missing_from_quotes(tmp_path, monkeypatch):
    data_dir = tmp_path / "var"
    ws = data_dir / "ws"
    ws.mkdir(parents=True)
    d = date(2026, 10, 30)
    path = ws / "bars_1m_20261030.jsonl"
    ts = "2026-10-30T10:05:00+05:30"
    path.write_text(
        json.dumps({"sym": "DLF", "ts": ts, "o": 690, "h": 691, "l": 689, "c": 690.5, "v": 1}) + "\n",
        encoding="utf-8",
    )
    now_ms = int(datetime(2026, 10, 30, 10, 6, tzinfo=IST).timestamp() * 1000)
    mq = resolve_mark("DLF", quotes={"quotes": []}, data_dir=data_dir, lake=None, now_ms=now_ms, trade_date=d)
    assert mq is not None and mq.mark_source == "bar_1m" and mq.mark == 690.5


def test_daily_when_no_quote_or_bar(tmp_path):
    data_dir = tmp_path / "var"
    lake = Lake(data_dir / "lake")
    lake.write_daily(
        "ADANIPORTS",
        pd.DataFrame(
            [
                {
                    "date": 20261030,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1,
                    "source": "t",
                    "adj_factor": 1.0,
                }
            ]
        ),
    )
    now_ms = int(datetime(2026, 10, 30, 16, 0, tzinfo=IST).timestamp() * 1000)
    mq = resolve_mark(
        "ADANIPORTS",
        quotes={"quotes": []},
        data_dir=data_dir,
        lake=lake,
        now_ms=now_ms,
    )
    assert mq is not None and mq.mark_source == "daily" and mq.mark == 100.5


def test_build_paper_equity_uses_mark_not_entry(tmp_path, monkeypatch):
    from engine.state import init_db

    data_dir = tmp_path / "var"
    ws = data_dir / "ws"
    ws.mkdir(parents=True)
    path = ws / "bars_1m_20261030.jsonl"
    path.write_text(
        json.dumps({"sym": "X", "ts": "2026-10-30T10:00:00+05:30", "c": 150.0}) + "\n",
        encoding="utf-8",
    )
    from config.settings import get_settings, reset_settings_cache

    reset_settings_cache()
    monkeypatch.setattr(get_settings(), "data_dir", str(data_dir))
    conn = init_db(data_dir / "engine.db")
    conn.execute(
        "INSERT INTO paper_cycles(started_ms, starting_wallet, wallet, peak_wallet, status, config_json) "
        "VALUES (1, 100000, 80000, 100000, 'running', '{}')"
    )
    entry_ms = int(datetime(2026, 10, 25, 10, 0, tzinfo=IST).timestamp() * 1000)
    sql = (
        "INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, "
        "stop_init, stop_now, mode, status) VALUES ('X','B','T',1,100,?,?,90,90,'paper','open')"
    )
    conn.execute(
        sql,
        (entry_ms, 100.0),
    )
    conn.commit()
    now_ms = int(datetime(2026, 10, 30, 10, 5, tzinfo=IST).timestamp() * 1000)
    body = build_paper(conn, {"quotes": [], "ts_ms": now_ms}, now_ms)
    assert body["positions"][0]["mark"] == 150.0
    assert body["equity"] == 80000 + 100 * 150.0
