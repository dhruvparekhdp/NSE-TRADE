"""V1b-1: global cues + FII/DII from fixtures. No network (PLAN_V2 V1b-1, AGENTS rule 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data import global_cues as gc
from data.flows import (
    FlowRow,
    flow_is_stale,
    latest_flow_before,
    parse_fii_dii,
    refresh_flows,
    save_flow,
)
from data.nse_http import NseUnavailable
from engine import state

FIX = Path(__file__).parent / "fixtures"
MIN = 60_000


def _load(name: str) -> dict:
    return json.loads((FIX / "cues" / name).read_text())


@pytest.fixture
def conn(tmp_path):
    c = state.init_db(tmp_path / "e.db")
    yield c
    c.close()


def _spec(key="SPX"):
    return next(s for s in gc.load_cue_specs() if s.key == key)


def test_cues_json_has_every_planned_yahoo_symbol():
    want = {
        "^GSPC", "^IXIC", "^DJI", "ES=F", "NQ=F", "^GDAXI", "^FTSE", "^FCHI", "^STOXX50E", "^N225",
        "^HSI", "^KS11", "INR=X", "DX-Y.NYB", "BZ=F", "GC=F", "^TNX", "^NSEI", "^INDIAVIX",
    }
    got = {s.symbol for s in gc.load_cue_specs() if s.source == "yahoo"}
    assert got == want
    gift = next(s for s in gc.load_cue_specs() if s.key == "GIFTNIFTY")
    assert gift.source == "gift" and gift.symbol is None


def test_migration_003_creates_opening_tables_and_is_idempotent(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in (
        "global_cues", "flows", "headlines", "preopen_snapshots",
        "opening_summary", "morning_brief", "sentiment_daily",
    ):
        assert t in names
    assert state.migrate(conn) >= 3  # 003_opening; later phases may add 004+
    assert state.migrate(conn) >= 3


def test_migrate_applies_a_lower_numbered_file_added_later(tmp_path, monkeypatch):
    """V4's 002 must still apply on a database that already has V1b's 003."""
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "001_a.sql").write_text(
        "CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_ms INTEGER NOT NULL);"
        "CREATE TABLE a(x);"
    )
    (mdir / "003_c.sql").write_text("CREATE TABLE c(x);")
    monkeypatch.setattr(state, "MIGRATIONS_DIR", mdir)
    conn = state.connect(tmp_path / "x.db")
    state.migrate(conn)
    (mdir / "002_b.sql").write_text("CREATE TABLE b(x);")
    state.migrate(conn)
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"a", "b", "c"} <= names
    conn.close()


def test_closed_market_is_stale_with_real_change_not_zero():
    payload = _load("yahoo_spx_closed.json")
    mkt_ms = payload["chart"]["result"][0]["meta"]["regularMarketTime"] * 1000
    row = gc.parse_yahoo_chart(payload, _spec(), now_ms=mkt_ms + 60 * MIN, interval_s=300)
    assert row is not None
    assert row.stale is True
    assert row.ref_close == 5020.0  # the session before the last one, not chartPreviousClose
    assert row.chg_pct == pytest.approx(0.3984, abs=1e-3)


def test_live_market_fresh_then_stale_after_two_intervals():
    payload = _load("yahoo_nifty_live.json")
    mkt_ms = payload["chart"]["result"][0]["meta"]["regularMarketTime"] * 1000
    spec = _spec("NIFTY")
    fresh = gc.parse_yahoo_chart(payload, spec, now_ms=mkt_ms + 2 * MIN, interval_s=300)
    old = gc.parse_yahoo_chart(payload, spec, now_ms=mkt_ms + 11 * MIN, interval_s=300)
    assert fresh.stale is False and old.stale is True
    assert fresh.chg_pct == pytest.approx((24260 - 24200) / 24200 * 100, abs=1e-3)


def test_unknown_previous_close_gives_none_not_zero():
    row = gc.parse_yahoo_chart(_load("yahoo_one_bar.json"), _spec("BRENT"), now_ms=1, interval_s=300)
    assert row is not None
    assert row.ref_close is None and row.chg_pct is None


def test_yahoo_error_payload_gives_no_row():
    assert gc.parse_yahoo_chart(_load("yahoo_empty.json"), _spec(), now_ms=1, interval_s=300) is None


def _fake_fetch(calls: list[str]):
    def fetch(symbol: str) -> dict:
        calls.append(symbol)
        if symbol == "^FTSE":
            raise TimeoutError("yahoo down")
        if symbol == "^HSI":
            return _load("yahoo_empty.json")
        return _load("yahoo_nifty_live.json" if symbol == "^NSEI" else "yahoo_spx_closed.json")

    return fetch


def test_refresh_stores_rows_skips_failures_and_never_fetches_gift(conn):
    calls: list[str] = []
    now = 1_792_700_000_000
    rows = gc.refresh_cues(conn, now_ms=now, fetch=_fake_fetch(calls), interval_s=300)
    keys = {r.key for r in rows}
    assert "FTSE" not in keys and "HSI" not in keys  # failed / empty: nothing invented
    assert "GIFTNIFTY" not in keys and None not in calls
    assert len(keys) == 17
    stored = conn.execute("SELECT COUNT(*) AS n FROM global_cues").fetchone()["n"]
    assert stored == 17


def test_latest_cues_has_no_lookahead_and_flags_dead_poller(conn):
    spec = _spec("NIFTY")
    payload = _load("yahoo_nifty_live.json")
    mkt_ms = payload["chart"]["result"][0]["meta"]["regularMarketTime"] * 1000
    for off in (0, 5, 10):
        gc.save_cue_rows(
            conn,
            [gc.parse_yahoo_chart(payload, spec, now_ms=mkt_ms + off * MIN, interval_s=300)],
        )
    at_7 = gc.latest_cues(conn, now_ms=mkt_ms + 7 * MIN, interval_s=300)["NIFTY"]
    assert at_7.ts_ms == mkt_ms + 5 * MIN  # the 10-minute row is in the future
    dead = gc.latest_cues(conn, now_ms=mkt_ms + 60 * MIN, interval_s=300)["NIFTY"]
    assert dead.stale is True  # our own poll stopped


def test_window_change_ignores_stale_snapshots(conn):
    def row(ts, last, stale):
        return gc.CueRow(ts, "BRENT", last, None, None, "yahoo", stale, ts)

    gc.save_cue_rows(
        conn,
        [row(0, 70.0, True), row(30 * MIN, 80.0, False), row(60 * MIN, 82.4, False)],
    )
    chg = gc.window_change_pct(conn, "BRENT", now_ms=60 * MIN, window_ms=120 * MIN)
    assert chg == pytest.approx(3.0)  # 80 -> 82.4, the stale 70 is ignored
    assert gc.window_change_pct(conn, "BRENT", now_ms=30 * MIN, window_ms=120 * MIN) is None


def test_overnight_proxy_uses_futures_and_asia_only(conn):
    now = 1_792_700_000_000
    mk = now - 60 * MIN

    def r(k, c):
        return gc.CueRow(now, k, 1.0, c, 1.0, "yahoo", True, mk)

    cues = {"ES": r("ES", 0.4), "NQ": r("NQ", 0.6), "N225": r("N225", -0.2), "SPX": r("SPX", 5.0)}
    assert gc.overnight_proxy_pct(cues, now_ms=now) == pytest.approx(0.2667, abs=1e-3)
    assert gc.overnight_proxy_pct({}, now_ms=now) is None


# ---- flows ---------------------------------------------------------------------------------


def _fii():
    return json.loads((FIX / "nse" / "fiidii.json").read_text())


def test_parse_fii_dii_fixture():
    row = parse_fii_dii(_fii())
    assert row == FlowRow("2026-10-22", fii_net_cr=-2500.25, dii_net_cr=2345.57)
    assert parse_fii_dii({"unexpected": 1}) is None
    assert parse_fii_dii([]) is None


def test_refresh_flows_stores_and_survives_nse_block(conn):
    row = refresh_flows(conn, lambda url: _fii())
    assert row is not None
    got = conn.execute("SELECT * FROM flows").fetchone()
    assert got["trade_date"] == "2026-10-22" and got["final"] == 0

    def blocked(url):
        raise NseUnavailable("403")

    assert refresh_flows(conn, blocked) is None
    assert conn.execute("SELECT COUNT(*) AS n FROM flows").fetchone()["n"] == 1


def test_final_flow_is_not_overwritten_by_provisional(conn):
    save_flow(conn, FlowRow("2026-10-22", -2400.0, 2300.0, "nse_final", final=True))
    save_flow(conn, FlowRow("2026-10-22", -2500.0, 2345.0))
    assert conn.execute("SELECT fii_net_cr FROM flows").fetchone()["fii_net_cr"] == -2400.0


def test_flow_known_at_open_is_the_previous_session_only(conn):
    save_flow(conn, FlowRow("2026-10-22", -1.0, 1.0))
    save_flow(conn, FlowRow("2026-10-23", -9.0, 9.0))
    assert latest_flow_before(conn, "2026-10-23").trade_date == "2026-10-22"
    assert latest_flow_before(conn, "2026-10-22") is None
    assert flow_is_stale(None, "2026-10-23") is True
    assert flow_is_stale(latest_flow_before(conn, "2026-10-23"), "2026-10-23") is False
    assert flow_is_stale(FlowRow("2026-10-01", 0, 0), "2026-10-23") is True
