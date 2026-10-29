# ruff: noqa: E402
"""C17 paper book + C13 market_filter (no network)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from config.settings import set_runtime_override
from core.types import Signal
from data.lake import Lake
from engine.paper_jobs import (
    _wallet,
    daily_bars_ready,
    ensure_paper_cycle,
    equity_at_cost,
    job_eod_fill,
    job_scan,
    load_portfolio_state,
)
from engine.state import init_db
from strategies.base import Context

IST = ZoneInfo("Asia/Kolkata")


def _bar_ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST).timestamp() * 1000)


def _write_daily(lake: Lake, sym: str, d: date, close: float = 100.0) -> None:
    lake.write_daily(
        sym,
        pd.DataFrame(
            [
                {
                    "date": int(d.strftime("%Y%m%d")),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1000,
                    "delivery_qty": 0,
                    "source": "test",
                    "adj_factor": 1.0,
                }
            ]
        ),
    )


def _two_day_lake(lake: Lake, sym: str, scan: date, close: float = 2500.0) -> None:
    prev = scan - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    _write_daily(lake, sym, prev, close * 0.99)
    _write_daily(lake, sym, scan, close)
    _two_day_lake_nifty(lake, scan)


def _two_day_lake_nifty(lake: Lake, scan: date) -> None:
    prev = scan - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    _write_daily(lake, "NIFTYBEES", prev, 99.0)
    _write_daily(lake, "NIFTYBEES", scan, 100.0)


class _Pick:
    id = "S_a"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars, ctx: Context) -> list[Signal]:  # noqa: ANN001
        last = bars.closed()[-1]
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=last.close,
                stop=last.close * 0.95,
                target=None,
                time_exit_ms=None,
                strategy=self.id,
                book="B",
                role="pick",
            )
        ]


class _PickB:
    id = "S_b"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars, ctx: Context) -> list[Signal]:  # noqa: ANN001
        last = bars.closed()[-1]
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=last.close,
                stop=last.close * 0.95,
                target=None,
                time_exit_ms=None,
                strategy=self.id,
                book="B",
                role="pick",
            )
        ]


def test_max_open_swing_counts_pending_in_one_scan(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    for i, sym in enumerate("ABCDEF"):
        _two_day_lake(lake, sym, d, 2000.0 + i)
    _two_day_lake_nifty(lake, d)
    conn = init_db(tmp_path / "e.db")
    for sym in "ABCDEF":
        conn.execute(
            "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
            (sym, "1", 0.05, 1, 1, 1),
        )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.f2_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.load_sector_map", lambda: None)
    set_runtime_override("market_filter", "off")
    rows = job_scan(
        conn,
        lake,
        trade_date=d,
        enabled=["S_a"],
        symbols=list("ABCDEF"),
        write=True,
    )
    picks = [r for r in rows if r["role"] == "pick"]
    pending = [r for r in picks if r["decision"] == "pending"]
    blocked = [r for r in picks if r["skip_reason"] == "max_open_swing"]
    assert len(pending) == 4
    assert len(blocked) >= 2
    st = load_portfolio_state(conn)
    assert st.open_swing == 4


def test_second_strategy_skips_already_in_symbol(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    reg.ALL["S_b"] = _PickB()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "DRREDDY", d, 1500.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("DRREDDY", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.f2_skip_reason", lambda *a, **k: None)
    set_runtime_override("market_filter", "off")
    rows = job_scan(
        conn,
        lake,
        trade_date=d,
        enabled=["S_a", "S_b"],
        symbols=["DRREDDY"],
        write=True,
    )
    picks = [r for r in rows if r["role"] == "pick"]
    assert sum(1 for r in picks if r["decision"] == "pending") == 1
    assert any(r["skip_reason"] == "already_in_symbol" for r in picks)


def test_fill_debits_wallet_and_refuses_cash(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d0 = date(2026, 10, 26)
    d1 = d0 + timedelta(days=1)
    while d1.weekday() >= 5:
        d1 += timedelta(days=1)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "X", d0, 100.0)
    _write_daily(lake, "X", d1, 100.0)
    _write_daily(lake, "NIFTYBEES", d1, 100.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.f2_skip_reason", lambda *a, **k: None)
    set_runtime_override("market_filter", "off")
    ensure_paper_cycle(conn)
    job_scan(conn, lake, trade_date=d0, enabled=["S_a"], symbols=["X"], write=True)
    w0 = _wallet(conn)
    fills = job_eod_fill(conn, lake, trade_date=d1)
    w1 = _wallet(conn)
    assert fills and fills[0].get("status") == "filled"
    assert w1 < w0
    held = sum(r["qty"] * r["avg_price"] for r in conn.execute("SELECT qty, avg_price FROM holdings"))
    assert abs(w1 + held - w0) < 500.0
    from core.types import SizeResult

    conn.execute("UPDATE paper_cycles SET wallet=500 WHERE status='running'")
    conn.commit()
    conn.execute(
        "INSERT INTO pending_orders(trade_date, symbol, book, strategy, side, qty, limit_price, "
        "stop, target, status, created_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (d1.isoformat(), "Y", "B", "S_a", 1, 10, 100.0, 95.0, None, "pending", 1),
    )
    _write_daily(lake, "Y", d1, 100.0)
    conn.commit()
    monkeypatch.setattr(
        "engine.paper_jobs.size", lambda *a, **k: SizeResult(10, 1000.0, "ok")
    )
    conn.execute("DELETE FROM paper_runs WHERE trade_date=? AND job='eod_fill'", (d1.isoformat(),))
    conn.commit()
    bad = job_eod_fill(conn, lake, trade_date=d1)
    assert any(r.get("status") == "cash" for r in bad)


def test_market_filter_off_stores_would_skip_reason(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "X", d, 2500.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr(
        "engine.paper_jobs.f1_f2_reasons", lambda _c: ("market_filter_f1_vol", None)
    )
    set_runtime_override("market_filter", "off")
    job_scan(conn, lake, trade_date=d, enabled=["S_a"], symbols=["X"], write=True)
    row = conn.execute(
        "SELECT features_json FROM signals WHERE symbol='X' AND role='pick' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    feat = json.loads(row["features_json"])
    assert feat.get("would_skip_reason") == "market_filter_f1_vol"
    assert feat.get("decision") == "pending"


def test_market_filter_on_blocks_pick(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "X", d, 2500.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr(
        "engine.paper_jobs.f1_f2_reasons", lambda _c: ("market_filter_f1_vol", None)
    )
    set_runtime_override("market_filter", "on")
    rows = job_scan(conn, lake, trade_date=d, enabled=["S_a"], symbols=["X"], write=True)
    pick = next(r for r in rows if r["role"] == "pick")
    assert pick["skip_reason"] == "market_filter_f1_vol"
    assert pick["decision"] != "pending"


def test_market_filter_shadow_no_pending(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "X", d, 2500.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    set_runtime_override("market_filter", "shadow")
    rows = job_scan(conn, lake, trade_date=d, enabled=["S_a"], symbols=["X"], write=True)
    assert all(r["decision"] == "shadow" for r in rows if r["role"] == "pick")
    n = conn.execute("SELECT COUNT(*) AS n FROM pending_orders").fetchone()["n"]
    assert n == 0


def test_validate_market_filter_whitelist(monkeypatch):
    from web import portal_data as pd

    set_runtime_override("market_filter", "on")
    assert pd.validate_setting("market_filter", "shadow") == "shadow"

    class _Live:
        mode = "live"

    monkeypatch.setattr(pd, "get_settings", lambda: _Live())
    with pytest.raises(ValueError, match="live mode"):
        pd.validate_setting("market_filter", "off")


def test_daily_bars_ready_probe(tmp_path):
    lake = Lake(tmp_path / "lake")
    d = date(2026, 10, 29)
    assert not daily_bars_ready(lake, d)
    _write_daily(lake, "NIFTYBEES", d)
    assert daily_bars_ready(lake, d)


def test_second_fill_sizes_on_equity_not_depleted_cash(tmp_path, monkeypatch):
    """After ~21k buy on 1L, slot must still clear ₹20k CNC floor (equity ≈ 1L)."""
    import strategies.registry as reg
    from config.settings import get_settings
    from core.risk import limits_from_settings, size

    reg.ALL["S_a"] = _Pick()
    d0 = date(2026, 10, 26)
    d1 = d0 + timedelta(days=1)
    while d1.weekday() >= 5:
        d1 += timedelta(days=1)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "A", d0, 2500.0)
    _two_day_lake(lake, "B", d0, 2500.0)
    _write_daily(lake, "A", d1, 2500.0)
    _write_daily(lake, "B", d1, 2500.0)
    _write_daily(lake, "NIFTYBEES", d1, 100.0)
    conn = init_db(tmp_path / "e.db")
    for sym in ("A", "B"):
        conn.execute(
            "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
            (sym, "1", 0.05, 1, 1, 1),
        )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.f2_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.load_sector_map", lambda: None)
    set_runtime_override("market_filter", "off")
    ensure_paper_cycle(conn)
    job_scan(conn, lake, trade_date=d0, enabled=["S_a"], symbols=["A", "B"], write=True)
    fills = job_eod_fill(conn, lake, trade_date=d1)
    assert any(f.get("status") == "filled" for f in fills)
    eq = equity_at_cost(conn)
    assert eq > 95_000
    lim = limits_from_settings(get_settings())
    sz = size(2500.0, 2500.0 * 0.95, eq, lim.risk_per_trade_pct, 0.05, "B", lim)
    assert sz.qty > 0 and sz.value >= lim.min_position_cnc_inr - 1.0
    assert sum(1 for f in fills if f.get("status") == "filled") >= 2
    fills2 = job_eod_fill(conn, lake, trade_date=d1)
    assert not fills2


def test_pending_sizing_failure_does_not_reserve_slot(tmp_path, monkeypatch):
    from core.types import SizeResult

    d1 = date(2026, 10, 27)
    lake = Lake(tmp_path / "lake")
    _write_daily(lake, "Y", d1, 100.0)
    _write_daily(lake, "NIFTYBEES", d1, 100.0)
    conn = init_db(tmp_path / "e.db")
    ensure_paper_cycle(conn)
    conn.execute(
        "INSERT INTO pending_orders(trade_date, symbol, book, strategy, side, qty, limit_price, "
        "stop, target, status, created_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (d1.isoformat(), "Y", "B", "S_a", 1, 10, 100.0, 95.0, None, "pending", 1),
    )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.size", lambda *a, **k: SizeResult(0, 0.0, "below_min_cnc_position"))
    job_eod_fill(conn, lake, trade_date=d1)
    row = conn.execute("SELECT status FROM pending_orders WHERE symbol='Y'").fetchone()
    assert row["status"] == "below_min_cnc_position"
    st = load_portfolio_state(conn, pending_after=d1)
    assert st.open_swing == 0


def test_eod_fill_and_scan_idempotent_per_date(tmp_path, monkeypatch):
    import strategies.registry as reg

    reg.ALL["S_a"] = _Pick()
    d = date(2026, 10, 26)
    lake = Lake(tmp_path / "lake")
    _two_day_lake(lake, "X", d, 2500.0)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    monkeypatch.setattr("engine.paper_jobs.f1_skip_reason", lambda *a, **k: None)
    monkeypatch.setattr("engine.paper_jobs.load_sector_map", lambda: None)
    set_runtime_override("market_filter", "off")

    def snap():
        return (
            conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"],
            conn.execute("SELECT COUNT(*) AS n FROM pending_orders").fetchone()["n"],
            conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"],
        )

    job_eod_fill(conn, lake, trade_date=d)
    job_scan(conn, lake, trade_date=d, enabled=["S_a"], symbols=["X"], write=True)
    once = snap()
    job_eod_fill(conn, lake, trade_date=d)
    job_scan(conn, lake, trade_date=d, enabled=["S_a"], symbols=["X"], write=True)
    assert snap() == once
