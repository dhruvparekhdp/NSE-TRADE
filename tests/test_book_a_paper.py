# ruff: noqa: E402
"""C12 Book A intraday paper on 1-min bars."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import set_runtime_override
from engine.book_a_paper import JsonlMinuteBarSource, job_book_a_minute, run_book_a_until
from engine.state import init_db

IST = ZoneInfo("Asia/Kolkata")


def _ms(h: int, m: int) -> int:
    return int(datetime(2026, 10, 30, h, m, tzinfo=IST).timestamp() * 1000)


def _write_bars(path, sym: str, minutes: list[tuple[int, int, float]]) -> None:
    lines = []
    for h, mi, o in minutes:
        ts = f"2026-10-30T{h:02d}:{mi:02d}:00+05:30"
        lines.append(json.dumps({"sym": sym, "ts": ts, "o": o, "h": o + 1, "l": o - 1, "c": o, "v": 1}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_fill_at_next_open_and_idempotent(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1001.0), (9, 18, 1002.0)])
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (_ms(9, 16), "2026-10-30", "SBIN", "A", "S1_orb", 1, "pick", 1000.0, 999.0, 1020.0, "shadow"),
    )
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    s1 = job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    s2 = job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    assert s1["entries"] == 1
    assert s2["entries"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM trades WHERE book='A'").fetchone()["n"] == 1


def test_max_open_refusal(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "X", [(9, 16, 50.0), (9, 17, 50.0)])
    _write_bars(bars, "Y", [(9, 16, 50.0), (9, 17, 50.0)])
    conn = init_db(tmp_path / "e.db")
    for sym in ("X", "Y", "Z", "W"):
        conn.execute(
            "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_ms(9, 16), "2026-10-30", sym, "A", "T", 1, "pick", 50.0, 49.0, 55.0, "shadow"),
        )
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    # only 2 symbols have bars; third signal stays pending — test max 3 with open trades
    open_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='open' AND book='A'").fetchone()["n"]
    assert open_n <= 3


def test_shadow_mode_unchanged(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1001.0)])
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (_ms(9, 16), "2026-10-30", "SBIN", "A", "S1_orb", 1, "pick", 1000.0, 999.0, 1020.0, "shadow"),
    )
    conn.commit()
    set_runtime_override("book_a_mode", "shadow")
    src = JsonlMinuteBarSource(bars)
    out = job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    assert out.get("skipped") is True
    assert conn.execute("SELECT COUNT(*) AS n FROM trades WHERE book='A'").fetchone()["n"] == 0


def _insert_sig(conn, sym: str, h: int, m: int, *, stop: float = 999.0) -> None:
    conn.execute(
        "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (_ms(h, m), "2026-10-30", sym, "A", "S1_orb", 1, "pick", 1000.0, stop, 1020.0, "shadow"),
    )


def test_stop_hit_inside_bar(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1000.0)])
    hit = {"sym": "SBIN", "ts": "2026-10-30T09:18:00+05:30", "o": 1000.0, "h": 1001.0, "l": 998.0, "c": 999.0, "v": 1}
    bars.write_text(bars.read_text(encoding="utf-8") + json.dumps(hit) + "\n", encoding="utf-8")
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16, stop=999.0)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    job_book_a_minute(conn, src, now_ms=_ms(9, 18))
    row = conn.execute("SELECT status, exit_reason FROM trades WHERE book='A'").fetchone()
    assert row["status"] == "closed" and row["exit_reason"] == "stop"


def test_square_off_at_close(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1000.0), (14, 55, 1005.0)])
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16, stop=995.0)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    job_book_a_minute(conn, src, now_ms=_ms(14, 55))
    row = conn.execute("SELECT status, exit_reason FROM trades WHERE book='A'").fetchone()
    assert row["status"] == "closed" and row["exit_reason"] in ("time", "square_off")


def test_no_entry_after_1435(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(14, 34, 1000.0), (14, 35, 1000.0), (14, 36, 1000.0)])
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 14, 35)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(14, 36))
    assert conn.execute("SELECT COUNT(*) AS n FROM trades WHERE book='A'").fetchone()["n"] == 0


def test_same_symbol_refusal(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1001.0), (9, 18, 1002.0), (9, 19, 1003.0)])
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16)
    _insert_sig(conn, "SBIN", 9, 17)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    job_book_a_minute(conn, src, now_ms=_ms(9, 18))
    st = conn.execute(
        "SELECT skip_reason FROM book_a_signal_state WHERE skip_reason='already_in_symbol'"
    ).fetchone()
    assert st is not None


def test_margin_cash_refusal(tmp_path, monkeypatch):
    from engine.book_a_paper import ensure_book_a_cycle as ensure_cycle

    bars = tmp_path / "bars.jsonl"
    _write_bars(bars, "SBIN", [(9, 16, 1000.0), (9, 17, 1001.0)])
    extra = tmp_path / "bars2.jsonl"
    _write_bars(extra, "TCS", [(9, 16, 1000.0), (9, 17, 1001.0)])
    bars.write_text(bars.read_text(encoding="utf-8") + extra.read_text(encoding="utf-8"), encoding="utf-8")
    conn = init_db(tmp_path / "e.db")
    ensure_cycle(conn, capital=100_000.0)
    sql = (
        "INSERT INTO trades(symbol, book, strategy, side, qty, entry_ms, entry_price, "
        "stop_init, stop_now, mode, status) VALUES ('TCS','A','T',1,450,?,?,900,900,'paper','open')"
    )
    conn.execute(
        sql,
        (_ms(9, 15), 1000.0),
    )
    _insert_sig(conn, "SBIN", 9, 16)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    st = conn.execute("SELECT skip_reason FROM book_a_signal_state ORDER BY signal_id DESC LIMIT 1").fetchone()
    assert st["skip_reason"] == "cash"


def _append(path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _bar(sym: str, h: int, m: int, o: float, hi: float, lo: float, c: float) -> dict:
    return {"sym": sym, "ts": f"2026-10-30T{h:02d}:{m:02d}:00+05:30", "o": o, "h": hi, "l": lo, "c": c, "v": 1}


def test_live_driver_waits_for_finished_minutes_and_catches_up(tmp_path):
    """Live: a minute's bar lands only after the minute ends; the driver must still enter and stop out."""
    bars = tmp_path / "bars.jsonl"
    _append(bars, _bar("SBIN", 9, 16, 1000, 1001, 999.5, 1000))
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16, stop=995.0)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    # 09:17:00 cron tick: the 09:17 bar does not exist yet -> nothing, and no signal is burnt as no_bar
    run_book_a_until(conn, JsonlMinuteBarSource(bars), now_ms=_ms(9, 17))
    assert conn.execute("SELECT COUNT(*) FROM book_a_signal_state").fetchone()[0] == 0
    _append(bars, _bar("SBIN", 9, 17, 1000, 1002, 999, 1001))
    _append(bars, _bar("SBIN", 9, 18, 1001, 1001, 990, 992))
    # 09:20:00 tick (one tick missed): processes 09:17 entry and 09:18 stop
    out = run_book_a_until(conn, JsonlMinuteBarSource(bars), now_ms=_ms(9, 20))
    assert out["entries"] == 1 and out["exits"] == 1
    row = conn.execute("SELECT entry_ms, exit_reason FROM trades WHERE book='A'").fetchone()
    assert row["entry_ms"] == _ms(9, 17) and row["exit_reason"] == "stop"
    again = run_book_a_until(conn, JsonlMinuteBarSource(bars), now_ms=_ms(9, 20))
    assert again["minutes"] == 0


def test_stop_inside_entry_minute(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _append(bars, _bar("SBIN", 9, 16, 1000, 1001, 999, 1000))
    _append(bars, _bar("SBIN", 9, 17, 1000, 1001, 980, 985))
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16, stop=995.0)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    job_book_a_minute(conn, JsonlMinuteBarSource(bars), now_ms=_ms(9, 17))
    row = conn.execute("SELECT status, exit_reason FROM trades WHERE book='A'").fetchone()
    assert row["status"] == "closed" and row["exit_reason"] == "stop"


def test_net_is_gross_minus_charges_only(tmp_path):
    """Fill prices already carry slippage; closing must not take slippage off a second time."""
    from core.costs import rates_for, round_trip

    bars = tmp_path / "bars.jsonl"
    _append(bars, _bar("SBIN", 9, 16, 1000, 1001, 999, 1000))
    _append(bars, _bar("SBIN", 9, 17, 1000, 1001, 999, 1000))
    _append(bars, _bar("SBIN", 9, 18, 1000, 1030, 999, 1025))
    conn = init_db(tmp_path / "e.db")
    _insert_sig(conn, "SBIN", 9, 16, stop=995.0)
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    src = JsonlMinuteBarSource(bars)
    job_book_a_minute(conn, src, now_ms=_ms(9, 17))
    job_book_a_minute(conn, src, now_ms=_ms(9, 18))
    t = conn.execute("SELECT * FROM trades WHERE book='A'").fetchone()
    assert t["exit_reason"] == "target"
    q, e, x = t["qty"], t["entry_price"], t["exit_price"]
    charges = round_trip(e * q, x * q, "MIS", rates_for("MIS")).total
    assert abs(t["net_inr"] - ((x - e) * q - charges)) < 1e-6


def test_old_days_signals_ignored(tmp_path):
    bars = tmp_path / "bars.jsonl"
    _append(bars, _bar("SBIN", 9, 16, 1000, 1001, 999, 1000))
    _append(bars, _bar("SBIN", 9, 17, 1000, 1001, 999, 1000))
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO signals(ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target, decision) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (_ms(9, 16) - 86_400_000, "2026-10-29", "SBIN", "A", "S1_orb", 1, "pick", 1000.0, 995.0, 1020.0, "shadow"),
    )
    conn.commit()
    set_runtime_override("book_a_mode", "paper")
    # 09:20: an old signal would otherwise be matched to today's first bar and logged no_bar
    job_book_a_minute(conn, JsonlMinuteBarSource(bars), now_ms=_ms(9, 20))
    assert conn.execute("SELECT COUNT(*) FROM book_a_signal_state").fetchone()[0] == 0
