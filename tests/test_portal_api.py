"""V5-2: the portal endpoints return exactly the PLAN_V2 §7 shapes (fixtures) and never invent numbers."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import bcrypt
import pytest
from aiohttp.test_utils import TestClient, TestServer

from config.settings import reset_settings_cache
from core.clock import IST, Clock
from engine.state import init_db
from lab.ledger import record_trial
from web.app import create_app
from web.keys import reset_reveal_rate_for_tests
from web.reasons import REASONS, reason_text

FIXTURES = Path(__file__).parent / "fixtures" / "portal"
NOW_MS = int(datetime(2026, 10, 23, 10, 0, tzinfo=IST).timestamp() * 1000)  # a Friday, market open

# endpoint -> (fixture name, needs admin login)
ENDPOINTS = {
    "/api/portal/meta": ("meta", False),
    "/api/quotes": ("quotes", False),
    "/api/market": ("market", False),
    "/api/swing": ("swing", False),
    "/api/paper": ("paper", False),
    "/api/portal/signals?days=14": ("signals", False),
    "/api/lab": ("lab", False),
    "/api/golive": ("golive", False),
    "/api/guard": ("guard", False),
    "/api/data-health": ("data_health", False),
    "/api/opening": ("opening", False),
    "/api/sentiment": ("sentiment", False),
    "/api/headlines?hours=24": ("headlines", False),
    "/api/events?limit=10": ("events", False),
    "/api/health": ("health", False),
    "/api/universe": ("universe", False),
    "/api/keys": ("keys", True),
    "/api/settings": ("settings", True),
    "/api/tables": ("tables", True),
}
# objects whose keys are data (symbol names, table names), not shape
FREE_FORM = {"data_health.lake.sources", "tables.tables"}
# the only objects allowed to be null: a strategy that has never been through the lab has no report
NULLABLE = {"lab.strategies[].last_report"}


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def assert_same_shape(want, got, path: str) -> None:
    """Every key of the fixture is in the response and vice versa, at every level."""
    if isinstance(want, dict):
        if got is None and re.sub(r"\[\d+\]", "[]", path) in NULLABLE:
            return
        assert isinstance(got, dict), f"{path}: expected an object, got {type(got).__name__}"
        if path in FREE_FORM:
            return
        assert set(got) == set(want), f"{path}: keys differ, extra={set(got) - set(want)}, missing={set(want) - set(got)}"
        for k in want:
            assert_same_shape(want[k], got[k], f"{path}.{k}")
    elif isinstance(want, list):
        assert isinstance(got, list), f"{path}: expected a list"
        if want and got:
            for i, item in enumerate(got):
                assert_same_shape(want[0], item, f"{path}[{i}]")


def numeric_leaves(x, path=""):
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return
    if isinstance(x, (int, float)):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from numeric_leaves(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from numeric_leaves(v, f"{path}[{i}]")


async def make_client(monkeypatch, tmp_path, *, db: bool) -> TestClient:
    password = "test-pass"
    monkeypatch.setenv("PORTAL_ADMIN_HASH", bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    monkeypatch.setenv("SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    reset_reveal_rate_for_tests()
    conn = init_db(tmp_path / "engine.db") if db else None
    app = create_app(db=conn, clock=Clock(_now_ms=NOW_MS))
    cli = TestClient(TestServer(app))
    await cli.start_server()
    cli.conn = conn
    return cli


@pytest.fixture
async def empty(monkeypatch, tmp_path):
    cli = await make_client(monkeypatch, tmp_path, db=False)
    assert (await cli.post("/api/login", json={"password": "test-pass"})).status == 200
    yield cli
    await cli.close()


@pytest.fixture
async def empty_db(monkeypatch, tmp_path):
    cli = await make_client(monkeypatch, tmp_path, db=True)
    assert (await cli.post("/api/login", json={"password": "test-pass"})).status == 200
    yield cli
    await cli.close()


# Opening tables come from migration 003; only paper_cycles is V4 (create if missing for portal tests).
V1B_DDL = """
CREATE TABLE IF NOT EXISTS paper_cycles (
  id INTEGER PRIMARY KEY, started_ms INTEGER NOT NULL, ended_ms INTEGER,
  starting_wallet REAL NOT NULL, target_wallet REAL, wallet REAL NOT NULL, peak_wallet REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'running', outcome TEXT, config_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS global_cues (
  ts_ms INTEGER NOT NULL, key TEXT NOT NULL, last REAL, chg_pct REAL, ref_close REAL,
  source TEXT NOT NULL, stale INTEGER DEFAULT 0, mkt_ts_ms INTEGER, PRIMARY KEY (ts_ms, key));
CREATE TABLE IF NOT EXISTS flows (
  trade_date TEXT PRIMARY KEY, fii_net_cr REAL, dii_net_cr REAL, source TEXT, final INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS headlines (
  id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, published_ms INTEGER, source TEXT, title TEXT NOT NULL,
  link TEXT, event_type TEXT, symbol TEXT, score REAL, confidence REAL, market TEXT, external_id TEXT UNIQUE,
  nifty_move_next_60m REAL);
CREATE TABLE IF NOT EXISTS preopen_snapshots (
  trade_date TEXT NOT NULL, ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL, iep REAL,
  prev_close REAL, chg_pct REAL, buy_qty INTEGER, sell_qty INTEGER, final INTEGER DEFAULT 0, source TEXT,
  PRIMARY KEY (trade_date, ts_ms, symbol));
CREATE TABLE IF NOT EXISTS opening_summary (
  trade_date TEXT NOT NULL, symbol TEXT NOT NULL, open REAL, prev_close REAL, gap_pct REAL,
  imbalance REAL, or15_high REAL, or15_low REAL, or30_high REAL, or30_low REAL, first5_vol_x REAL,
  gap_filled_ms INTEGER, close REAL, open_to_close_pct REAL, open_type TEXT,
  PRIMARY KEY (trade_date, symbol));
CREATE TABLE IF NOT EXISTS morning_brief (trade_date TEXT PRIMARY KEY, built_ms INTEGER, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sentiment_daily (
  trade_date TEXT PRIMARY KEY, composite REAL, parts_json TEXT NOT NULL, breadth_adv INTEGER,
  breadth_dec INTEGER, risk_off_alarm INTEGER DEFAULT 0);
"""


def seed(conn: sqlite3.Connection, data_dir: Path) -> None:
    """A small but complete world: V4/V1b tables as PLAN_V2 §5 defines them, plus trades and signals."""
    conn.executescript(V1B_DDL)
    day = 86_400_000
    t = "INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, stop_init, stop_now, exit_ms, exit_price, exit_reason, gross_inr, costs_inr, net_inr, r_mult, mode, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    conn.execute(t, ("RELIANCE", "B", "S6_swing", 1, 15, NOW_MS - 4 * day, 1402.5, 1340.0, 1362.5, None, None, None, None, None, None, None, "paper", "open"))
    conn.execute(t, ("TCS", "B", "S6_swing", 1, 10, NOW_MS - 30 * day, 3800.0, 3700.0, 3700.0, NOW_MS - 10 * day, 3980.0, "trail", 1800.0, 150.0, 1650.0, 1.8, "paper", "closed"))
    conn.execute(t, ("INFY", "B", "S6_swing", 1, 12, NOW_MS - 25 * day, 1500.0, 1450.0, 1450.0, NOW_MS - 8 * day, 1450.0, "stop", -600.0, 120.0, -720.0, -1.0, "paper", "closed"))
    s = "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision, skip_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    conn.execute(s, (NOW_MS - day, "2026-10-22", "INFY", "B", "S6_swing", 1, "pick", 1510.0, 1450.0, None, "skipped", "max_open_swing"))
    conn.execute(s, (NOW_MS - 2 * day, "2026-10-21", "RELIANCE", "B", "S6_swing", 1, "pick", 1402.5, 1340.0, None, "taken", None))
    conn.execute(s, (NOW_MS - 2 * day, "2026-10-21", "RELIANCE", "B", "S6_swing", -1, "mirror", 1402.5, 1465.0, None, "skipped", "mirror"))
    conn.execute(s, (NOW_MS - 2 * day, "2026-10-21", "SBIN", "A", "S1_orb", 1, "pick", 800.0, 796.0, None, "shadow", "book_a_shadow"))
    # (near_circuit skip omitted so takeskip.skip.n stays 1 for the contract test)
    record_trial(conn, strategy="S6_swing", params={}, data_from="2012-01-02", data_to="2026-10-22", period="2012-2026",
                 n=140, avg_r=0.12, win_pct=41.0, passed=False, report_path="reports/s6.json")
    record_trial(conn, strategy="S6_swing", params={}, data_from="2012-01-02", data_to="2026-10-22", period="2019-2026",
                 n=90, avg_r=0.2, win_pct=45.0, passed=True)
    conn.execute("INSERT INTO paper_cycles(started_ms, starting_wallet, wallet, peak_wallet, config_json) VALUES (?,?,?,?,?)",
                 (NOW_MS - 10 * day, 100000.0, 97000.0, 101000.0, "{}"))
    conn.execute("INSERT INTO flows VALUES ('2026-10-22', -1250.0, 1810.0, 'nse', 1)")
    conn.execute(
        "INSERT INTO global_cues(ts_ms, key, last, chg_pct, ref_close, source, stale, mkt_ts_ms) "
        "VALUES (?, 'GIFTNIFTY', 24600.0, 0.22, 24546.0, 'x', 0, ?)",
        (NOW_MS - 1000, NOW_MS - 1000),
    )
    conn.execute(
        "INSERT INTO global_cues(ts_ms, key, last, chg_pct, ref_close, source, stale, mkt_ts_ms) "
        "VALUES (?, 'INDIAVIX', 13.4, -1.0, 13.5, 'x', 0, ?)",
        (NOW_MS - 1000, NOW_MS - 1000),
    )
    conn.execute("INSERT INTO headlines(ts_ms, source, title, event_type, score, external_id) VALUES (?,?,?,?,?,?)",
                 (NOW_MS - 3_600_000, "ET Markets", "RBI holds repo rate", "india_macro", 0.1, "a1"))
    conn.execute("INSERT INTO morning_brief VALUES ('2026-10-23', ?, ?)", (NOW_MS - 3_600_000, json.dumps({"fii_net_cr": -1250.0, "composite": 0.12})))
    conn.execute("INSERT INTO preopen_snapshots VALUES ('2026-10-23', ?, 'NIFTY', 24500.0, 24420.0, 0.33, 600, 400, 1, 'x')", (NOW_MS - 3_000_000,))
    conn.execute("INSERT INTO preopen_snapshots VALUES ('2026-10-23', ?, 'ADANIENT', 2410.0, 2377.0, 1.4, 300, 100, 1, 'x')", (NOW_MS - 3_000_000,))
    conn.execute("INSERT INTO opening_summary(trade_date, symbol, gap_pct, imbalance, or15_high, or15_low, open_type) VALUES ('2026-10-22','NIFTY',-0.1,-0.05,24560.0,24480.0,'flat')")
    conn.execute("INSERT INTO sentiment_daily VALUES ('2026-10-23', 0.12, ?, 31, 18, 0)", (json.dumps([{"key": "us", "label": "US overnight", "value": 0.4, "weight": 0.3, "contribution": 0.12, "ts_ms": NOW_MS, "stale": False}]),))
    conn.execute("INSERT INTO events(ts_ms, kind, json) VALUES (?, 'setting_changed', '{}')", (NOW_MS,))
    conn.commit()
    (data_dir / "quotes_cache.json").write_text(json.dumps({
        "ts_ms": NOW_MS - 40_000, "source": "yahoo_chart",
        "quotes": [{"symbol": "RELIANCE", "ltp": 1431.0, "prev_close": 1420.0, "volume": 5_000_000},
                   {"symbol": "TCS", "ltp": 3890.5, "prev_close": 3901.0, "volume": 1_200_000}]}), encoding="utf-8")


@pytest.fixture
async def seeded(monkeypatch, tmp_path):
    cli = await make_client(monkeypatch, tmp_path, db=True)
    seed(cli.conn, tmp_path)
    assert (await cli.post("/api/login", json={"password": "test-pass"})).status == 200
    yield cli
    await cli.close()


# ---------------------------------------------------------------- contract: keys match the fixture
@pytest.mark.parametrize("url", list(ENDPOINTS))
async def test_every_endpoint_matches_its_fixture_with_no_database(empty, url):
    name, _admin = ENDPOINTS[url]
    resp = await empty.get(url)
    assert resp.status == 200, url
    assert_same_shape(fixture(name), await resp.json(), name)


@pytest.mark.parametrize("url", list(ENDPOINTS))
async def test_every_endpoint_matches_its_fixture_with_an_empty_database(empty_db, url):
    name, _admin = ENDPOINTS[url]
    resp = await empty_db.get(url)
    assert resp.status == 200, url
    assert_same_shape(fixture(name), await resp.json(), name)


@pytest.mark.parametrize("url", list(ENDPOINTS))
async def test_every_endpoint_matches_its_fixture_with_rows(seeded, url):
    name, _admin = ENDPOINTS[url]
    resp = await seeded.get(url)
    assert resp.status == 200, url
    assert_same_shape(fixture(name), await resp.json(), name)


@pytest.mark.parametrize("url", [u for u, (_, admin) in ENDPOINTS.items() if admin])
async def test_admin_endpoints_need_the_login_cookie(monkeypatch, tmp_path, url):
    cli = await make_client(monkeypatch, tmp_path, db=False)
    try:
        assert (await cli.get(url)).status == 401
    finally:
        await cli.close()


async def test_every_fixture_has_an_endpoint():
    used = {name for name, _ in ENDPOINTS.values()}
    assert {p.stem for p in FIXTURES.glob("*.json")} == used


# ---------------------------------------------------------------- empty states: never invent numbers
@pytest.mark.parametrize("url", ["/api/market", "/api/swing", "/api/paper", "/api/portal/signals", "/api/lab", "/api/guard",
                                 "/api/opening", "/api/sentiment", "/api/headlines", "/api/quotes", "/api/data-health"])
async def test_empty_database_gives_zero_or_null_never_made_up_numbers(empty_db, url):
    body = await (await empty_db.get(url)).json()
    for path, value in numeric_leaves(body):
        if path.startswith(".rules"):  # the book's configured rules, not data
            continue
        if ".session." in path:  # live clock countdown, not invented market data
            continue
        assert value == 0, f"{url}{path} = {value}: an empty database must not produce numbers"


async def test_empty_states_say_nothing_is_running(empty_db):
    paper = await (await empty_db.get("/api/paper")).json()
    assert paper["enabled"] is False and paper["running"] is False
    assert paper["cycle"]["id"] is None and paper["equity"] is None
    assert paper["summary"]["win_rate_pct"] is None and paper["summary"]["expectancy_per_trade"] is None
    swing = await (await empty_db.get("/api/swing")).json()
    assert swing["open"] == [] and swing["closed"]["n"] == 0 and swing["closed"]["avg_r"] is None
    market = await (await empty_db.get("/api/market")).json()
    assert market["nifty"]["ltp"] is None and market["india_vix"] is None and market["fii_net_cr"] is None
    opening = await (await empty_db.get("/api/opening")).json()
    assert opening["brief"]["built_ms"] is None and opening["history"] == []


# ---------------------------------------------------------------- real values from real rows
async def test_swing_open_position_math_and_closed_stats(seeded):
    body = await (await seeded.get("/api/swing")).json()
    (pos,) = body["open"]
    assert pos["symbol"] == "RELIANCE" and pos["mark"] == 1431.0
    assert pos["r_now"] == pytest.approx((1431.0 - 1402.5) / (1402.5 - 1340.0))
    assert pos["unrealised_inr"] == pytest.approx(28.5 * 15)
    assert pos["sessions_held"] + pos["sessions_left"] == 20
    assert body["closed"]["n"] == 2 and body["closed"]["win_rate"] == 50.0
    assert body["closed"]["avg_r"] == pytest.approx(0.4) and body["closed"]["total_r"] == pytest.approx(0.8)
    assert [r["symbol"] for r in body["closed"]["last"]] == ["INFY", "TCS"]  # newest exit first
    assert body["takeskip"]["take"]["n"] == 1 and body["takeskip"]["skip"]["n"] == 1


async def test_paper_cycle_equity_and_summary(seeded):
    body = await (await seeded.get("/api/paper")).json()
    assert body["enabled"] and body["running"]
    assert body["cycle"]["starting_wallet"] == 100000.0 and body["cycle"]["wallet"] == 97000.0
    assert body["equity"] == pytest.approx(97000.0 + 15 * 1431.0)  # cash + shares at the last quote
    assert body["unrealised"] == pytest.approx(427.5)
    assert body["summary"]["trades"] == 2 and body["summary"]["net_pnl"] == pytest.approx(930.0)
    assert body["summary"]["expectancy_per_trade"] == pytest.approx(465.0)
    assert set(body["summary"]["costs"]) == {"brokerage", "stt", "exchange", "sebi", "stamp", "gst", "dp", "slippage"}
    assert len(body["positions"]) == 1 and len(body["history"]) == 2


async def test_signals_filters_refused_panel_and_plain_english(seeded):
    body = await (await seeded.get("/api/portal/signals?days=14")).json()
    assert len(body["rows"]) == 4  # the 60-day-old one is outside 14 days
    skipped = next(r for r in body["rows"] if r["symbol"] == "INFY")
    assert skipped["skip_reason"] == "max_open_swing"
    assert skipped["reason_text"] == "swing book is full: maximum open positions reached"
    assert {r["reason"] for r in body["refused"]} == {"max_open_swing", "mirror", "book_a_shadow"}
    wide = await (await seeded.get("/api/portal/signals?days=90")).json()
    assert len(wide["rows"]) == 4
    for query, expect in (("book=A", {"SBIN"}), ("role=mirror", {"RELIANCE"}), ("decision=taken", {"RELIANCE"}), ("strategy=S1_orb", {"SBIN"})):
        got = await (await seeded.get(f"/api/portal/signals?days=14&{query}")).json()
        assert {r["symbol"] for r in got["rows"]} == expect, query


async def test_signals_inputs_are_clamped_not_trusted(seeded):
    assert (await seeded.get("/api/portal/signals?days=abc&limit=-5")).status == 200
    assert (await seeded.get("/api/portal/signals?days=99999999")).status == 200
    hostile = await seeded.get("/api/portal/signals?strategy=%27%3B%20DROP%20TABLE%20signals%3B--")
    assert (await hostile.json())["rows"] == []
    assert seeded.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 4


async def test_lab_counts_trials_per_strategy(seeded):
    body = await (await seeded.get("/api/lab")).json()
    assert body["trials_total"] == 2
    s6 = next(s for s in body["strategies"] if s["id"] == "S6_swing")
    assert s6["trials"] == 2 and s6["passed"] == 1 and s6["last_report"]["passed"] is True
    never_run = next(s for s in body["strategies"] if s["id"] != "S6_swing")
    assert never_run["trials"] == 0 and never_run["last_report"] is None


async def test_market_uses_flows_cues_and_quotes_when_present(seeded):
    body = await (await seeded.get("/api/market")).json()
    assert body["fii_net_cr"] == -1250.0 and body["dii_net_cr"] == 1810.0
    assert body["india_vix"] == 13.4 and body["gift_nifty_chg_pct"] == 0.22
    assert body["nifty"]["ltp"] is None  # no Nifty quote cached: stays empty, not guessed


async def test_opening_sentiment_headlines_read_the_v1b_tables(seeded):
    opening = await (await seeded.get("/api/opening")).json()
    assert opening["trade_date"] == "2026-10-23" and opening["phase"] == "day"  # NOW_MS is 10:00 IST
    assert opening["brief"]["fii_net_cr"] == -1250.0 and opening["brief"]["built_ms"] is not None
    assert opening["preopen"]["nifty"]["iep"] == 24500.0
    assert opening["preopen"]["nifty"]["imbalance"] == pytest.approx(0.2)
    assert opening["preopen"]["movers"][0]["symbol"] == "ADANIENT"
    assert opening["scorecard"]["breadth"] == {"adv": 31, "dec": 18}
    assert opening["history"][0]["open_type"] == "flat"
    sentiment = await (await seeded.get("/api/sentiment")).json()
    assert sentiment["composite"] == 0.12 and sentiment["label"] == "neutral" and sentiment["parts"][0]["key"] == "us"
    heads = await (await seeded.get("/api/headlines?hours=24")).json()
    assert [h["title"] for h in heads["rows"]] == ["RBI holds repo rate"] and heads["tags"] == [{"event_type": "india_macro", "n": 1}]
    assert (await (await seeded.get("/api/headlines?hours=24&tag=nope")).json())["rows"] == []


async def test_meta_is_paper_with_session_and_derived_times(empty):
    body = await (await empty.get("/api/portal/meta")).json()
    assert body["mode"] == "paper" and body["live_orders"] is False
    assert body["session"]["state"] == "OPEN" and body["session"]["next_label"]
    assert body["session"]["next_change_ms"] > NOW_MS
    assert body["calendar_ok"] is True and body["calendar_year_loaded"] == 2026
    assert body["costs_verified"] is False
    assert body["squareoff_at"] and body["no_entry_after"]


async def test_quotes_endpoint_computes_change_from_prev_close(seeded):
    body = await (await seeded.get("/api/quotes")).json()
    rel = next(q for q in body["quotes"] if q["symbol"] == "RELIANCE")
    assert rel["chg_pct"] == pytest.approx((1431.0 - 1420.0) / 1420.0 * 100)
    assert body["source"] == "yahoo_chart" and body["ts_ms"] == NOW_MS - 40_000


async def test_guard_flags_and_golive_gates_are_computed_server_side(seeded):
    guard = await (await seeded.get("/api/guard")).json()
    assert {f["id"] for f in guard["flags"]} >= {"kill_switch", "daily_loss", "floor", "feed_stale", "reconcile", "calendar", "risk_off"}
    assert guard["floor_ok"] is True and guard["feed"]["quotes_age_s"] == 40
    golive = await (await seeded.get("/api/golive")).json()
    gates = {g["id"]: g for g in golive["gates"]}
    assert golive["verdict"] == "NOT READY"
    assert gates["lab_gate"]["ok"] is True  # one passed trial was recorded
    assert gates["paper_weeks"]["ok"] is False and gates["owner_yes"]["ok"] is False
    assert gates["calendar"]["ok"] is True


async def test_golive_owner_yes_gate_cannot_be_ticked(empty_db):
    body = await (await empty_db.get("/api/golive")).json()
    gates = {g["id"]: g for g in body["gates"]}
    assert gates["owner_yes"]["ok"] is False and body["verdict"] == "NOT READY"
    assert gates["real_data"]["ok"] is False and gates["paper_trades"]["ok"] is False


# ---------------------------------------------------------------- the lake
async def test_data_health_reads_the_lake(monkeypatch, tmp_path):
    import pandas as pd

    from data.lake import Lake

    lake = Lake(tmp_path / "lake")
    dates = [20261019, 20261020, 20261022]  # 21 Oct is a trading day with no row
    df = pd.DataFrame({"date": dates, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10, "source": "bhav"})
    lake.write_daily("SBIN", df)
    lake.write_daily("FAKE", df.assign(source="synth"))
    cli = await make_client(monkeypatch, tmp_path, db=False)
    try:
        from web import portal_data

        portal_data._lake_cache.clear()
        body = await (await cli.get("/api/data-health")).json()
        assert body["lake"]["symbols"] == 2 and body["lake"]["synthetic_files"] == 1
        assert body["lake"]["first_date"] == "2026-10-19" and body["lake"]["last_date"] == "2026-10-22"
        assert "2026-10-21" in body["lake"]["missing_days"]
        assert body["bhav"]["last_date"] == "2026-10-22" and body["corp_actions_applied"] is False
        golive = await (await cli.get("/api/golive")).json()
        real = next(g for g in golive["gates"] if g["id"] == "real_data")
        assert real["ok"] is False and "1 synthetic" in real["detail"]
    finally:
        await cli.close()


# ---------------------------------------------------------------- reasons.py
def test_every_risk_reason_has_plain_english():
    src = (Path(__file__).parent.parent / "core" / "risk.py").read_text()
    codes = set(re.findall(r'return False, "(\w+)"', src))
    assert codes, "no reasons found in core/risk.py"
    for code in codes:
        assert code in REASONS, f"core/risk.py can refuse with {code!r} but web/reasons.py has no sentence for it"
        assert "_" not in reason_text(code)


def test_reason_text_examples_from_the_plan():
    assert reason_text("below_min_position") == "position under ₹20,000: costs would eat too much"
    assert reason_text("below_min_position", min_position_inr=25000) == "position under ₹25,000: costs would eat too much"
    assert reason_text("near_circuit") == "too close to today's price band"
    assert reason_text("results_day") == "results due within 3 days"
    assert reason_text("market_filter") == "Nifty volatility in the top third of the past year"
    assert reason_text("") == "" and reason_text(None) == ""
    assert reason_text("brand_new_code") == "brand new code"  # unknown codes are shown, not hidden


# ---------------------------------------------------------------- settings + universe writes
async def test_settings_are_whitelisted_logged_and_never_touch_live_flags(seeded):
    ok = await seeded.post("/api/settings", json={"key": "max_open_swing", "value": 3})
    assert ok.status == 200 and (await ok.json())["value"] == 3
    row = seeded.conn.execute("SELECT json FROM events WHERE kind='setting_changed' ORDER BY id DESC LIMIT 1").fetchone()
    assert json.loads(row["json"]) == {"key": "max_open_swing", "old": 4, "new": 3}
    ok_mf = await seeded.post("/api/settings", json={"key": "market_filter", "value": "shadow"})
    assert ok_mf.status == 200
    for key, value in (("live_orders", True), ("mode", "live"), ("market_filter", "nifty_vol"), ("max_open_swing", 99),
                       ("risk_per_trade_pct", 5), ("book_a_mode", "paper"), ("kill_switch", "yes")):
        bad = await seeded.post("/api/settings", json={"key": key, "value": value})
        assert bad.status == 400, (key, value)
    meta = await (await seeded.get("/api/portal/meta")).json()
    assert meta["live_orders"] is False and meta["mode"] == "paper"


async def test_settings_writes_need_login(monkeypatch, tmp_path):
    cli = await make_client(monkeypatch, tmp_path, db=True)
    try:
        assert (await cli.post("/api/settings", json={"key": "kill_switch", "value": True})).status == 401
        assert (await cli.post("/api/universe/exclude", json={"symbol": "SBIN", "excluded": True})).status == 401
    finally:
        await cli.close()


async def test_universe_exclude_roundtrip(seeded):
    seeded.conn.execute("INSERT INTO instruments(symbol, tick_size, in_universe, updated_ms) VALUES ('SBIN', 0.05, 1, ?)", (int(time.time() * 1000),))
    seeded.conn.commit()
    resp = await seeded.post("/api/universe/exclude", json={"symbol": "sbin", "excluded": True})
    assert (await resp.json())["excluded"] == ["SBIN"]
    uni = await (await seeded.get("/api/universe")).json()
    assert uni["rows"] == [{"symbol": "SBIN", "excluded": True}]
    swing = await (await seeded.get("/api/swing")).json()
    assert swing["rules"]["excluded"] == ["SBIN"]
    assert (await seeded.post("/api/universe/exclude", json={"symbol": "x;drop", "excluded": True})).status == 400


async def test_tables_endpoint_hides_anything_secret_looking(seeded):
    seeded.conn.execute("CREATE TABLE app_settings_history (key TEXT, masked TEXT)")
    seeded.conn.execute("INSERT INTO app_settings_history VALUES ('angel_pin', 'ab•••yz')")
    seeded.conn.commit()
    body = await (await seeded.get("/api/tables?limit=5")).json()
    assert "signals" in body["tables"] and "app_settings_history" not in body["tables"]
    assert body["tables"]["signals"]["count"] == 4


async def test_health_lists_memory_budget_and_sources(empty):
    body = await (await empty.get("/api/health")).json()
    assert body["memory_limit_mb"] == 600
    assert {s["id"] for s in body["sources"]} == {"quotes", "angel"}
    assert body["jobs"] == []  # no scheduler in the test app
