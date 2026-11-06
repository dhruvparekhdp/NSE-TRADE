"""Paper/shadow scheduled jobs: sessions, idempotency, MIS square-off, no broker orders."""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

from broker.live_guard import live_orders_allowed as real_live_orders_allowed
from config.settings import reset_settings_cache
from core.types import Bar, Signal
from engine.scheduled_jobs import (
    cron_at,
    generate_signals,
    ist_epoch_ms,
    refresh_market_data,
    snapshot_performance,
    square_off_mis,
)
from engine.state import init_db

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "engine" / "scheduled_jobs.py"


def at(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return ist_epoch_ms(year, month, day, hour, minute)


@pytest.fixture
def db(tmp_path):
    conn = init_db(tmp_path / "engine.db")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _smartapi_order_methods_explode(monkeypatch):
    """A mocked SmartAPI whose order methods fail the test if a job reaches them."""
    calls: list[str] = []

    class SmartConnect:
        def __init__(self, *_a, **_k) -> None:
            calls.append("init")

        def placeOrder(self, *_a, **_k) -> None:  # noqa: N802
            calls.append("placeOrder")
            raise AssertionError("placeOrder")

        def modifyOrder(self, *_a, **_k) -> None:  # noqa: N802
            calls.append("modifyOrder")
            raise AssertionError("modifyOrder")

        def cancelOrder(self, *_a, **_k) -> None:  # noqa: N802
            calls.append("cancelOrder")
            raise AssertionError("cancelOrder")

    module = types.ModuleType("SmartApi")
    module.SmartConnect = SmartConnect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "SmartApi", module)

    def boom(name: str):
        def _inner(*_a, **_k):
            calls.append(name)
            raise AssertionError(name)

        return _inner

    monkeypatch.setattr("broker.live_guard.place_order", boom("place_order"))
    monkeypatch.setattr("broker.live_guard.modify_order", boom("modify_order"))
    monkeypatch.setattr("broker.live_guard.cancel_order", boom("cancel_order"))
    yield calls
    assert calls == []


class _OneShot:
    """One deterministic book A signal. Geometry does not matter."""

    id = "T_fake"
    book = "A"
    timeframe = "1m"

    def on_bar(self, symbol: str, bars: object, ctx: object) -> list[Signal]:
        del bars, ctx
        return [
            Signal(
                ts_ms=at(2026, 1, 27, 10, 0),
                symbol=symbol,
                side=1,
                entry_ref=100.0,
                stop=99.0,
                target=102.0,
                time_exit_ms=None,
                strategy=self.id,
                book="A",
            )
        ]


def _bars(ms: int) -> dict[str, list[Bar]]:
    return {"RELIANCE": [Bar(ms, 100.0, 101.0, 99.0, 100.0, 10)]}


def _quote(symbol: str, ltp: str, ms: int) -> dict[str, object]:
    return {"symbol": symbol, "ltp": ltp, "volume": 10, "source": "test", "ts_ms": ms}


def _count(conn, sql: str, *args: object) -> int:
    return int(conn.execute(sql, args).fetchone()["n"])


def test_refresh_is_idempotent_and_signals_wait_for_the_open(db) -> None:
    early = at(2026, 1, 27, 8, 30)
    pre = at(2026, 1, 27, 9, 10)
    quote = _quote("RELIANCE", "100.50", early)
    first = refresh_market_data(db, now_ms=early, quotes=[quote])
    second = refresh_market_data(db, now_ms=early, quotes=[quote])
    assert first["status"] == "ok"
    assert first["quotes"] == 1
    assert second["quotes"] == 1
    assert _count(db, "SELECT COUNT(*) AS n FROM quote_snapshots") == 1
    assert db.execute("SELECT ltp FROM quote_snapshots").fetchone()["ltp"] == "100.50"
    assert _count(db, "SELECT COUNT(*) AS n FROM job_runs WHERE job = ?", "refresh_market_data") == 1

    skipped = generate_signals(
        db,
        now_ms=pre,
        bars_by_symbol=_bars(pre),
        strategies=[_OneShot()],
        book_a_mode="paper",
    )
    assert skipped["status"] == "skipped"
    assert skipped["reason"] == "session:PRE_OPEN"
    assert _count(db, "SELECT COUNT(*) AS n FROM signals") == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM trades") == 0


def test_shadow_signals_are_idempotent_and_do_not_open_trades(db) -> None:
    ms = at(2026, 1, 27, 10, 0)
    kwargs = {
        "now_ms": ms,
        "bars_by_symbol": _bars(ms),
        "strategies": [_OneShot()],
        "book_a_mode": "shadow",
    }
    first = generate_signals(db, **kwargs)
    second = generate_signals(db, **kwargs)
    assert first["status"] == "ok"
    assert first["signals"] == 1
    assert first["opened"] == 0
    assert second["signals"] == 1
    assert second["opened"] == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM signals") == 1
    assert _count(db, "SELECT COUNT(*) AS n FROM trades") == 0
    assert db.execute("SELECT decision FROM signals").fetchone()["decision"] == "shadow"
    assert _count(db, "SELECT COUNT(*) AS n FROM job_runs WHERE job = ?", "generate_signals") == 1


def test_mis_square_off_is_idempotent_and_leaves_cnc_open(db) -> None:
    morning = at(2026, 1, 27, 10, 0)
    before = at(2026, 1, 27, 14, 54)
    due = at(2026, 1, 27, 14, 55)
    refresh_market_data(db, now_ms=morning, quotes=[_quote("RELIANCE", "100", morning)])
    opened = generate_signals(
        db,
        now_ms=morning,
        bars_by_symbol=_bars(morning),
        strategies=[_OneShot()],
        book_a_mode="paper",
    )
    again = generate_signals(
        db,
        now_ms=morning,
        bars_by_symbol=_bars(morning),
        strategies=[_OneShot()],
        book_a_mode="paper",
    )
    assert opened["opened"] == 1
    assert again["opened"] == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM trades") == 1

    early = square_off_mis(db, now_ms=before, square_off_at="14:55")
    assert early["status"] == "not_due"
    assert db.execute("SELECT status FROM trades WHERE book = 'A'").fetchone()["status"] == "open"

    refresh_market_data(db, now_ms=due, quotes=[_quote("RELIANCE", "110", due)])
    db.execute(
        """
        INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, mode, status)
        VALUES ('TCS', 'B', 'S6_swing', 1, 1, ?, 200, 'paper', 'open')
        """,
        (morning,),
    )
    db.commit()

    first = square_off_mis(db, now_ms=due, square_off_at="14:55")
    mis = db.execute(
        "SELECT status, exit_reason, net_inr, costs_inr, gross_inr FROM trades WHERE book = 'A'"
    ).fetchone()
    assert first["closed"] == 1
    assert mis["status"] == "closed"
    assert mis["exit_reason"] == "square_off"
    assert mis["costs_inr"] > 0
    assert mis["gross_inr"] == pytest.approx(10.0)
    assert mis["net_inr"] < mis["gross_inr"]
    cnc = db.execute("SELECT status, exit_ms FROM trades WHERE book = 'B'").fetchone()
    assert cnc["status"] == "open"
    assert cnc["exit_ms"] is None

    second = square_off_mis(db, now_ms=due, square_off_at="14:55")
    mis_again = db.execute("SELECT net_inr, costs_inr, status FROM trades WHERE book = 'A'").fetchone()
    assert second["closed"] == 0
    assert mis_again["net_inr"] == mis["net_inr"]
    assert mis_again["costs_inr"] == mis["costs_inr"]
    assert _count(db, "SELECT COUNT(*) AS n FROM trades WHERE book = 'A' AND status = 'closed'") == 1
    assert db.execute("SELECT status FROM trades WHERE book = 'B'").fetchone()["status"] == "open"
    assert _count(db, "SELECT COUNT(*) AS n FROM job_runs WHERE job = ?", "square_off_mis") == 1
    assert _count(db, "SELECT COUNT(*) AS n FROM orders") == 0

    too_soon = at(2026, 1, 27, 15, 39)
    due_snap = at(2026, 1, 27, 15, 45)
    waiting = snapshot_performance(db, now_ms=too_soon, start_inr=100000)
    assert waiting["status"] == "not_due"
    assert _count(db, "SELECT COUNT(*) AS n FROM performance_snapshots") == 0
    shot = snapshot_performance(db, now_ms=due_snap, start_inr=100000)
    shot_again = snapshot_performance(db, now_ms=due_snap, start_inr=100000)
    assert shot["rows"] == 2
    assert shot_again["rows"] == 2
    book_a = db.execute(
        "SELECT realized_inr, trades FROM performance_snapshots WHERE book = 'A'"
    ).fetchone()
    book_b = db.execute(
        "SELECT realized_inr, trades FROM performance_snapshots WHERE book = 'B'"
    ).fetchone()
    book_a_again = db.execute(
        "SELECT realized_inr, trades FROM performance_snapshots WHERE book = 'A'"
    ).fetchone()
    assert book_a["trades"] == 1
    assert book_b["realized_inr"] == "0.00"
    assert book_b["trades"] == 0
    assert book_a_again["realized_inr"] == book_a["realized_inr"]
    assert _count(db, "SELECT COUNT(*) AS n FROM performance_snapshots") == 2
    assert _count(db, "SELECT COUNT(*) AS n FROM job_runs WHERE job = ?", "snapshot_performance") == 1


@pytest.mark.parametrize(("year", "month", "day"), [(2026, 1, 26), (2026, 1, 25)])
def test_jobs_skip_holidays_and_weekends(db, year: int, month: int, day: int) -> None:
    ms = at(year, month, day, 10, 0)
    late = at(year, month, day, 15, 45)
    quote = _quote("RELIANCE", "100", ms)
    for _ in range(2):
        refresh = refresh_market_data(db, now_ms=ms, quotes=[quote])
        signals = generate_signals(
            db, now_ms=ms, bars_by_symbol=_bars(ms), strategies=[_OneShot()], book_a_mode="paper"
        )
        square = square_off_mis(db, now_ms=late, square_off_at="14:55")
        snap = snapshot_performance(db, now_ms=late)
    assert refresh["status"] == "skipped"
    assert refresh["reason"] == "holiday"
    assert signals["status"] == "skipped"
    assert square["status"] == "skipped"
    assert snap["status"] == "skipped"
    assert _count(db, "SELECT COUNT(*) AS n FROM quote_snapshots") == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM signals") == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM trades") == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM performance_snapshots") == 0
    assert _count(db, "SELECT COUNT(*) AS n FROM job_runs") == 4


def test_jobs_skip_a_year_with_no_holiday_file(db) -> None:
    ms = at(2027, 1, 4, 10, 0)
    result = refresh_market_data(db, now_ms=ms, quotes=[_quote("RELIANCE", "100", ms)])
    assert result["status"] == "skipped"
    assert result["reason"] == "calendar_missing"
    assert _count(db, "SELECT COUNT(*) AS n FROM quote_snapshots") == 0


def test_square_off_must_be_before_1530_ist(db) -> None:
    assert cron_at("14:55") == "55 14 * * mon-fri"
    assert cron_at("15:29") == "29 15 * * mon-fri"
    with pytest.raises(ValueError, match="15:30"):
        cron_at("15:30")
    ms = at(2026, 1, 27, 15, 29)
    db.execute(
        """
        INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, mode, status)
        VALUES ('RELIANCE', 'A', 'T_fake', 1, 1, ?, 100, 'paper', 'open')
        """,
        (at(2026, 1, 27, 10, 0),),
    )
    db.commit()
    with pytest.raises(ValueError, match="15:30"):
        square_off_mis(db, now_ms=ms, square_off_at="15:30")
    assert db.execute("SELECT status FROM trades").fetchone()["status"] == "open"
    done = square_off_mis(db, now_ms=ms, square_off_at="15:29")
    assert done["closed"] == 1
    assert db.execute("SELECT status FROM trades").fetchone()["status"] == "closed"


def test_muhurat_uses_the_special_square_off_and_blocks_new_entries(db) -> None:
    morning = at(2026, 11, 8, 14, 30)
    too_early = at(2026, 11, 8, 14, 55)
    due = at(2026, 11, 8, 15, 10)
    signals = generate_signals(
        db,
        now_ms=morning,
        bars_by_symbol=_bars(morning),
        strategies=[_OneShot()],
        book_a_mode="paper",
        allow_special=False,
    )
    assert signals["status"] == "skipped"
    assert signals["reason"] == "session:MUHURAT"
    assert _count(db, "SELECT COUNT(*) AS n FROM signals") == 0
    refresh_market_data(db, now_ms=morning, quotes=[_quote("RELIANCE", "101", morning)])
    db.execute(
        """
        INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, mode, status)
        VALUES ('RELIANCE', 'A', 'T_fake', 1, 1, ?, 100, 'paper', 'open')
        """,
        (morning,),
    )
    db.commit()
    waiting = square_off_mis(db, now_ms=too_early, square_off_at="14:55")
    assert waiting["status"] == "not_due"
    assert db.execute("SELECT status FROM trades").fetchone()["status"] == "open"
    first = square_off_mis(db, now_ms=due, square_off_at="14:55")
    net = db.execute("SELECT net_inr, status FROM trades").fetchone()
    second = square_off_mis(db, now_ms=due, square_off_at="14:55")
    net_again = db.execute("SELECT net_inr FROM trades").fetchone()
    assert first["closed"] == 1
    assert net["status"] == "closed"
    assert second["closed"] == 0
    assert net_again["net_inr"] == net["net_inr"]


def test_jobs_consult_the_guard_even_when_it_reports_live(db, monkeypatch) -> None:
    seen = {"allowed": 0, "asserted": 0}

    def allowed() -> bool:
        seen["allowed"] += 1
        return True

    def asserted() -> None:
        seen["asserted"] += 1

    monkeypatch.setattr("engine.scheduled_jobs.live_orders_allowed", allowed)
    monkeypatch.setattr("engine.scheduled_jobs.assert_live_orders_allowed", asserted)
    ms = at(2026, 1, 27, 10, 0)
    refresh_market_data(db, now_ms=ms, quotes=[_quote("RELIANCE", "100", ms)])
    generate_signals(db, now_ms=ms, bars_by_symbol=_bars(ms), strategies=[_OneShot()], book_a_mode="shadow")
    square_off_mis(db, now_ms=at(2026, 1, 27, 14, 55))
    snapshot_performance(db, now_ms=at(2026, 1, 27, 15, 45))
    assert seen["allowed"] == 4
    assert seen["asserted"] == 4
    assert real_live_orders_allowed() is False


def test_scheduled_jobs_module_does_not_touch_order_apis() -> None:
    tree = ast.parse(JOBS.read_text(encoding="utf-8"), filename=str(JOBS))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("broker"):
            imported.append(node.module)
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names if alias.name.startswith(("broker", "SmartApi")))
        if isinstance(node, ast.Attribute) and node.attr in {"placeOrder", "modifyOrder", "cancelOrder"}:
            raise AssertionError(f"order attribute at line {node.lineno}")
    assert imported == ["broker.live_guard"]
    public = {"refresh_market_data", "generate_signals", "square_off_mis", "snapshot_performance"}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in public:
            calls = [
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            ]
            assert "_through_guard" in calls


def test_runner_schedule_and_holiday_jobs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQUARE_OFF_AT", "14:50")
    reset_settings_cache()
    from engine.runner import EngineRunner

    runner = EngineRunner()
    try:
        runner._schedule()
        trigger = str(runner.scheduler.get_job("square_off").trigger)
        assert "hour='14'" in trigger
        assert "minute='50'" in trigger
        assert runner.scheduler.get_job("generate_signals") is not None
    finally:
        runner.db.close()


@pytest.mark.asyncio
async def test_runner_jobs_skip_a_holiday_and_square_off_twice(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    from engine.runner import EngineRunner

    runner = EngineRunner()
    try:
        holiday = at(2026, 1, 26, 15, 45)
        skipped = await runner.job_refresh_instruments(now_ms=holiday)
        assert skipped is not None
        assert skipped["status"] == "skipped"
        assert (await runner.job_generate_signals(now_ms=holiday))["status"] == "skipped"
        assert (await runner.job_square_off(now_ms=holiday))["status"] == "skipped"
        assert (await runner.job_eod(now_ms=holiday))["status"] == "skipped"

        morning = at(2026, 1, 27, 10, 0)
        due = at(2026, 1, 27, 14, 55)
        refresh_market_data(runner.db, now_ms=morning, quotes=[_quote("RELIANCE", "110", morning)])
        runner.db.execute(
            """
            INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, mode, status)
            VALUES ('RELIANCE', 'A', 'T_fake', 1, 1, ?, 100, 'paper', 'open')
            """,
            (morning,),
        )
        runner.db.commit()
        first = await runner.job_square_off(now_ms=due)
        net = runner.db.execute("SELECT net_inr, status FROM trades").fetchone()
        second = await runner.job_square_off(now_ms=due)
        net_again = runner.db.execute("SELECT net_inr FROM trades").fetchone()
        assert first is not None and first["closed"] == 1
        assert net["status"] == "closed"
        assert second is not None and second["closed"] == 0
        assert net_again["net_inr"] == net["net_inr"]
        assert _count(runner.db, "SELECT COUNT(*) AS n FROM orders") == 0
    finally:
        runner.db.close()
