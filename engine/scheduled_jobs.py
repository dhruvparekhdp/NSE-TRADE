"""Paper and shadow scheduled jobs (plan A12 / A15 / V4 / V6).

Market refresh, signal generation, the paper book, and the end-of-day snapshot
run locally. They consult the live-order guard and never call SmartAPI
place, modify, or cancel. `assert_live_orders_allowed` raises when live is
off, so paper work checks `live_orders_allowed` first and still runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from broker.live_guard import assert_live_orders_allowed, live_orders_allowed
from core.clock import SessionState, session_state, to_ist
from core.costs import round_trip
from core.types import Bar
from data.calendar import Calendar, CalendarMissing, load_default_calendar

log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
# Cash session the ticket requires the MIS square-off to beat (plan V1-3).
REGULAR_CLOSE = time(15, 30)
# 15:40 is after the 15:30 cash close and after the 2026 closing auction (15:35).
REGULAR_SNAPSHOT_AT = time(15, 40)
PAPER_QTY = 1  # one virtual share; a re-run must not stack size, and this is not an order


def ist_epoch_ms(year: int, month: int, day: int, hour: int, minute: int) -> int:
    """UTC epoch ms for a clock time in Asia/Kolkata."""
    dt = datetime(year, month, day, hour, minute, tzinfo=IST)
    return int(dt.timestamp() * 1000)


def parse_hhmm(value: str) -> time:
    """Parse HH:MM. Rejects anything that is not a clock time."""
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"expected HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"expected HH:MM, got {value!r}")
    return time(hour, minute)


def require_square_off_before_close(hhmm: str) -> time:
    """MIS must be flat before 15:30 IST (plan V1-3). Refuse a later clock."""
    parsed = parse_hhmm(hhmm)
    if parsed >= REGULAR_CLOSE:
        raise ValueError(f"MIS square-off {hhmm} must be before 15:30 IST")
    return parsed


def cron_at(hhmm: str, *, days: str = "mon-fri") -> str:
    """Cron expression for a square-off clock that is already before 15:30 IST."""
    parsed = require_square_off_before_close(hhmm)
    return f"{parsed.minute} {parsed.hour} * * {days}"


def _through_guard() -> None:
    """Touch the live-order choke point and do not call an order method.

    Paper and shadow jobs have to keep running when the guard is closed.
    When it is open, `assert_live_orders_allowed` passes and the job still
    only writes SQLite.
    """
    if live_orders_allowed():
        assert_live_orders_allowed()


class _Gate:
    def __init__(self, day: date, status: str, reason: str, calendar: Calendar | None) -> None:
        self.day = day
        self.status = status
        self.reason = reason
        self.calendar = calendar

    @property
    def trade_date(self) -> str:
        return self.day.isoformat()


def _gate(now_ms: int) -> _Gate:
    """Trading day in IST, or a skip. A missing holiday file is not a trading day."""
    day = to_ist(now_ms).date()
    try:
        calendar = load_default_calendar()
        calendar.require_year(day.year)
    except CalendarMissing:
        return _Gate(day, "skipped", "calendar_missing", None)
    if not calendar.is_trading_day(day):
        if calendar.is_holiday(day) or day.weekday() >= 5:
            return _Gate(day, "skipped", "holiday", calendar)
        return _Gate(day, "skipped", "closed", calendar)
    return _Gate(day, "ok", "", calendar)


def _clock(now_ms: int) -> time:
    return to_ist(now_ms).timetz().replace(tzinfo=None)


def _money(value: Decimal) -> str:
    """Rupee string with two decimal places (half up). No float in the snapshot."""
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _save(conn: sqlite3.Connection, job: str, gate: _Gate, result: dict[str, Any], now_ms: int) -> dict[str, Any]:
    """Persist one job row per day. A re-run replaces that row."""
    payload = {"status": result.get("status", gate.status), "reason": result.get("reason", gate.reason), **result}
    payload["trade_date"] = gate.trade_date
    conn.execute(
        """
        INSERT INTO job_runs(job, idempotency_key, trade_date, result_json, ran_ms)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job, idempotency_key) DO UPDATE SET
            result_json = excluded.result_json,
            ran_ms = excluded.ran_ms
        """,
        (job, f"{job}:{gate.trade_date}", gate.trade_date, json.dumps(payload, sort_keys=True), int(now_ms)),
    )
    conn.commit()
    return payload


def _skip(conn: sqlite3.Connection, job: str, gate: _Gate, now_ms: int, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"status": gate.status, "reason": gate.reason, **extra}
    return _save(conn, job, gate, body, now_ms)


def refresh_market_data(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    quotes: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Store the latest local quote per symbol for this IST date (plan A12).

    The caller passes quotes it already has (the on-disk cache, or a test
    double). This function does not fetch Yahoo or the scrip master. Holidays
    and weekends write nothing. A second run with the same symbols updates
    the same rows.
    """
    _through_guard()
    gate = _gate(now_ms)
    if gate.status != "ok":
        return _skip(conn, "refresh_market_data", gate, now_ms, quotes=0)
    for raw in quotes:
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol or raw.get("ltp") is None:
            continue
        ltp = format(Decimal(str(raw["ltp"])), "f")
        volume = int(raw.get("volume") or 0)
        source = str(raw.get("source") or "cache")
        ts_ms = int(raw.get("ts_ms") or now_ms)
        conn.execute(
            """
            INSERT INTO quote_snapshots(trade_date, symbol, source, ltp, volume, ts_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date, symbol, source) DO UPDATE SET
                ltp = excluded.ltp,
                volume = excluded.volume,
                ts_ms = excluded.ts_ms
            """,
            (gate.trade_date, symbol, source, ltp, volume, ts_ms),
        )
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM quote_snapshots WHERE trade_date = ?",
        (gate.trade_date,),
    ).fetchone()["n"]
    return _save(conn, "refresh_market_data", gate, {"status": "ok", "reason": "", "quotes": int(n)}, now_ms)


def _record_mode(book: str, book_a_mode: str) -> str | None:
    """Book A follows the paper/shadow switch. Book B is recorded only, never squared as MIS."""
    if book == "A":
        if book_a_mode in {"paper", "shadow"}:
            return book_a_mode
        return None
    if book == "B":
        return "shadow"
    return None


def _strategies(strategies: Sequence[Any] | None, enabled: Sequence[str] | None) -> list[Any]:
    if strategies is not None:
        return list(strategies)
    from strategies.registry import ALL

    chosen = list(ALL.values())
    if enabled:
        want = set(enabled)
        chosen = [item for item in chosen if item.id in want]
    return chosen


def _bars_from_quotes(conn: sqlite3.Connection, trade_date: str) -> dict[str, list[Bar]]:
    rows = conn.execute(
        "SELECT symbol, ltp, volume, ts_ms FROM quote_snapshots WHERE trade_date = ?",
        (trade_date,),
    ).fetchall()
    out: dict[str, list[Bar]] = {}
    for row in rows:
        px = float(row["ltp"])
        out[str(row["symbol"])] = [
            Bar(int(row["ts_ms"]), px, px, px, px, int(row["volume"] or 0), source="cache")
        ]
    return out


def _insert_signal(
    conn: sqlite3.Connection,
    *,
    ts_ms: int,
    trade_date: str,
    symbol: str,
    book: str,
    strategy: str,
    side: int,
    role: str,
    price: float,
    stop: float,
    target: float | None,
    features: dict[str, Any],
    decision: str,
) -> tuple[int, bool]:
    """Return (signal id, created). The same bar must not insert a second signal."""
    existing = conn.execute(
        """
        SELECT id FROM signals
        WHERE trade_date = ? AND symbol = ? AND strategy = ? AND book = ? AND role = ? AND ts_ms = ?
        """,
        (trade_date, symbol, strategy, book, role, ts_ms),
    ).fetchone()
    if existing is not None:
        return int(existing["id"]), False
    cur = conn.execute(
        """
        INSERT INTO signals(
            ts_ms, trade_date, symbol, book, strategy, side, role, price, stop, target,
            features_json, decision, skip_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            ts_ms,
            trade_date,
            symbol,
            book,
            strategy,
            side,
            role,
            price,
            stop,
            target,
            json.dumps(features, sort_keys=True),
            decision,
        ),
    )
    return int(cur.lastrowid), True


def _open_paper_trade(
    conn: sqlite3.Connection,
    *,
    signal_id: int,
    symbol: str,
    book: str,
    strategy: str,
    side: int,
    price: float,
    stop: float,
    target: float | None,
    now_ms: int,
) -> bool:
    """One virtual paper share per signal. This is a SQLite row, not a broker order."""
    existing = conn.execute(
        "SELECT id FROM trades WHERE signal_id = ? AND mode = 'paper'",
        (signal_id,),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        """
        INSERT INTO trades(
            signal_id, symbol, book, strategy, side, qty, entry_ms, entry_price,
            stop_init, stop_now, target, gross_inr, costs_inr, net_inr, mode, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 'paper', 'open')
        """,
        (signal_id, symbol, book, strategy, side, PAPER_QTY, now_ms, price, stop, stop, target),
    )
    return True


def generate_signals(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    bars_by_symbol: dict[str, list[Bar]] | None = None,
    strategies: Sequence[Any] | None = None,
    book_a_mode: str = "shadow",
    enabled: Sequence[str] | None = None,
    allow_special: bool = False,
    no_entry_after: str = "14:35",
    square_off_at: str = "14:55",
) -> dict[str, Any]:
    """Record signals during the open session. Paper book A also opens one virtual share.

    Shadow records the signal and does not open a trade. No path calls the broker.
    Re-running the same bar does not insert another signal or another trade.
    """
    _through_guard()
    gate = _gate(now_ms)
    if gate.status != "ok" or gate.calendar is None:
        return _skip(conn, "generate_signals", gate, now_ms, signals=0, opened=0)
    state = session_state(
        now_ms,
        calendar=gate.calendar,
        no_entry_after=no_entry_after,
        square_off_at=square_off_at,
    )
    tradable = state == SessionState.OPEN or (state == SessionState.MUHURAT and allow_special)
    if not tradable:
        held = _Gate(gate.day, "skipped", f"session:{state.value}", gate.calendar)
        return _skip(conn, "generate_signals", held, now_ms, signals=0, opened=0)

    from strategies.base import BarView, Context

    bars = bars_by_symbol if bars_by_symbol is not None else _bars_from_quotes(conn, gate.trade_date)
    ctx = Context(trade_date=gate.trade_date)
    opened = 0
    for strategy in _strategies(strategies, enabled):
        strategy_book = str(getattr(strategy, "book", "A"))
        decision = _record_mode(strategy_book, book_a_mode)
        if decision is None:
            continue
        timeframe = str(getattr(strategy, "timeframe", "1m"))
        for symbol, series in bars.items():
            view = BarView(bars=list(series), decision_ms=now_ms, timeframe=timeframe)
            try:
                found = strategy.on_bar(symbol, view, ctx) or []
            except Exception as exc:  # noqa: BLE001 — one strategy must not stop the scan
                log.warning("signal scan %s %s failed: %s", getattr(strategy, "id", "?"), symbol, exc)
                continue
            for sig in found:
                book = str(sig.book or strategy_book)
                mode = _record_mode(book, book_a_mode)
                if mode is None:
                    continue
                signal_id, _created = _insert_signal(
                    conn,
                    ts_ms=int(sig.ts_ms),
                    trade_date=gate.trade_date,
                    symbol=str(sig.symbol),
                    book=book,
                    strategy=str(sig.strategy or getattr(strategy, "id", "")),
                    side=int(sig.side),
                    role=str(sig.role),
                    price=float(sig.entry_ref),
                    stop=float(sig.stop),
                    target=None if sig.target is None else float(sig.target),
                    features=dict(sig.features or {}),
                    decision=mode,
                )
                if mode == "paper" and _open_paper_trade(
                    conn,
                    signal_id=signal_id,
                    symbol=str(sig.symbol),
                    book=book,
                    strategy=str(sig.strategy or getattr(strategy, "id", "")),
                    side=int(sig.side),
                    price=float(sig.entry_ref),
                    stop=float(sig.stop),
                    target=None if sig.target is None else float(sig.target),
                    now_ms=now_ms,
                ):
                    opened += 1
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM signals WHERE trade_date = ?",
        (gate.trade_date,),
    ).fetchone()["n"]
    return _save(
        conn,
        "generate_signals",
        gate,
        {"status": "ok", "reason": "", "signals": int(n), "opened": opened},
        now_ms,
    )


def _square_off_clock(day: date, configured: str, calendar: Calendar) -> time:
    """Special sessions (Muhurat) use their own square-off, still before 15:30 IST."""
    special = calendar.special_session(day)
    chosen = special.square_off_at if special is not None and special.square_off_at else configured
    return require_square_off_before_close(chosen)


def _exit_ltp(conn: sqlite3.Connection, trade_date: str, symbol: str, entry: Decimal) -> Decimal:
    row = conn.execute(
        """
        SELECT ltp FROM quote_snapshots
        WHERE trade_date = ? AND symbol = ?
        ORDER BY ts_ms DESC LIMIT 1
        """,
        (trade_date, symbol),
    ).fetchone()
    if row is None:
        return entry
    return Decimal(str(row["ltp"]))


def square_off_mis(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    square_off_at: str = "14:55",
) -> dict[str, Any]:
    """Close open paper book A (MIS) at the configured IST time. CNC stays open.

    Only rows with status open are updated, so a second run does not book the
    P&L again. A clock at or after 15:30 IST is refused and nothing is closed.
    """
    _through_guard()
    gate = _gate(now_ms)
    if gate.status != "ok" or gate.calendar is None:
        return _skip(conn, "square_off_mis", gate, now_ms, closed=0)
    when = _square_off_clock(gate.day, square_off_at, gate.calendar)
    if _clock(now_ms) < when:
        held = _Gate(gate.day, "not_due", "before_square_off", gate.calendar)
        return _skip(conn, "square_off_mis", held, now_ms, closed=0)
    rows = conn.execute(
        """
        SELECT id, symbol, side, qty, entry_price FROM trades
        WHERE book = 'A' AND mode = 'paper' AND status = 'open'
        """
    ).fetchall()
    closed = 0
    for row in rows:
        entry = Decimal(str(row["entry_price"]))
        qty = int(row["qty"])
        side = int(row["side"])
        exit_px = _exit_ltp(conn, gate.trade_date, str(row["symbol"]), entry)
        gross = (exit_px - entry) * qty * side
        entry_value = float(entry * qty)
        exit_value = float(exit_px * qty)
        if side >= 0:
            costs = Decimal(str(round_trip(entry_value, exit_value, "MIS").total))
        else:
            costs = Decimal(str(round_trip(exit_value, entry_value, "MIS").total))
        net = gross - costs
        updated = conn.execute(
            """
            UPDATE trades
            SET exit_ms = ?, exit_price = ?, exit_reason = 'square_off', status = 'closed',
                gross_inr = ?, costs_inr = ?, net_inr = ?
            WHERE id = ? AND status = 'open'
            """,
            (now_ms, float(exit_px), float(gross), float(costs), float(net), int(row["id"])),
        )
        closed += int(updated.rowcount or 0)
    return _save(conn, "square_off_mis", gate, {"status": "ok", "reason": "", "closed": closed}, now_ms)


def _closed_totals(conn: sqlite3.Connection, trade_date: str) -> dict[tuple[str, str], tuple[Decimal, Decimal, int]]:
    rows = conn.execute(
        "SELECT book, mode, exit_ms, net_inr, costs_inr FROM trades WHERE status = 'closed'"
    ).fetchall()
    out: dict[tuple[str, str], tuple[Decimal, Decimal, int]] = {}
    for row in rows:
        if row["exit_ms"] is None:
            continue
        if to_ist(int(row["exit_ms"])).date().isoformat() != trade_date:
            continue
        key = (str(row["book"]), str(row["mode"]))
        net, costs, n = out.get(key, (Decimal("0"), Decimal("0"), 0))
        out[key] = (
            net + Decimal(str(row["net_inr"] or 0)),
            costs + Decimal(str(row["costs_inr"] or 0)),
            n + 1,
        )
    return out


def snapshot_performance(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    start_inr: float = 0.0,
) -> dict[str, Any]:
    """Write the day's paper P&L once. A re-run stores the same absolute totals.

    Regular days wait until 15:40 IST. A special session waits until its own close.
    Totals are computed from closed trades, not added to the previous snapshot.
    """
    _through_guard()
    gate = _gate(now_ms)
    if gate.status != "ok" or gate.calendar is None:
        return _skip(conn, "snapshot_performance", gate, now_ms, rows=0)
    special = gate.calendar.special_session(gate.day)
    threshold = parse_hhmm(special.close) if special is not None else REGULAR_SNAPSHOT_AT
    if _clock(now_ms) < threshold:
        held = _Gate(gate.day, "not_due", "before_close", gate.calendar)
        return _skip(conn, "snapshot_performance", held, now_ms, rows=0)
    totals = _closed_totals(conn, gate.trade_date)
    for book in ("A", "B"):
        net, costs, n = totals.get((book, "paper"), (Decimal("0"), Decimal("0"), 0))
        end = Decimal(str(start_inr)) + net
        conn.execute(
            """
            INSERT INTO performance_snapshots(
                trade_date, book, mode, realized_inr, costs_inr, trades, as_of_ms
            ) VALUES (?, ?, 'paper', ?, ?, ?, ?)
            ON CONFLICT(trade_date, book, mode) DO UPDATE SET
                realized_inr = excluded.realized_inr,
                costs_inr = excluded.costs_inr,
                trades = excluded.trades,
                as_of_ms = excluded.as_of_ms
            """,
            (gate.trade_date, book, _money(net), _money(costs), n, now_ms),
        )
        conn.execute(
            """
            INSERT INTO daily_pnl(
                trade_date, mode, book, start_inr, realized_inr, costs_inr, end_inr, trades
            ) VALUES (?, 'paper', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date, mode, book) DO UPDATE SET
                start_inr = excluded.start_inr,
                realized_inr = excluded.realized_inr,
                costs_inr = excluded.costs_inr,
                end_inr = excluded.end_inr,
                trades = excluded.trades
            """,
            (gate.trade_date, book, float(start_inr), float(net), float(costs), float(end), n),
        )
    n_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM performance_snapshots WHERE trade_date = ?",
        (gate.trade_date,),
    ).fetchone()["n"]
    return _save(conn, "snapshot_performance", gate, {"status": "ok", "reason": "", "rows": int(n_rows)}, now_ms)
