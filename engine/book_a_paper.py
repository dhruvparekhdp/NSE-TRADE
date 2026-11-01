"""Book A intraday paper on 1-min bars (C12 scoped). Bar source is pluggable for C6."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from config.settings import get_setting, get_settings
from core.costs import rates_for, round_trip
from core.exits import ExitRules, Position, fill_entry_at_open, step_exits
from core.risk import PortfolioState, can_open, limits_from_settings, size
from core.session_times import derive_engine_times
from core.ticks import round_buy_limit, round_sell_limit
from core.types import Bar, Signal

IST = ZoneInfo("Asia/Kolkata")
MIS_MARGIN_PCT = 20.0
NO_BAR_MS = 3 * 60 * 1000


class MinuteBarSource(Protocol):
    def bar_at_minute(self, symbol: str, minute_ms: int) -> Bar | None: ...
    def next_bar_after(self, symbol: str, after_ms: int) -> Bar | None: ...


@dataclass
class JsonlMinuteBarSource:
    """In-memory index of 1-min bars from the ws recorder JSONL (replay or live file)."""

    path: Path
    _index: dict[tuple[str, int], Bar] | None = None

    def _load(self) -> None:
        if self._index is not None:
            return
        idx: dict[tuple[str, int], Bar] = {}
        if not self.path.exists():
            self._index = idx
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sym = str(row.get("sym") or "").upper()
                ts = row.get("ts")
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=IST)
                    ts_ms = int(dt.timestamp() * 1000)
                else:
                    ts_ms = int(ts or 0)
                minute_ms = ts_ms // 60_000 * 60_000
                bar = Bar(
                    ts_ms=ts_ms,
                    open=float(row["o"]),
                    high=float(row["h"]),
                    low=float(row["l"]),
                    close=float(row["c"]),
                    volume=int(row.get("v") or 0),
                )
                key = (sym, minute_ms)
                if key not in idx or bar.ts_ms >= idx[key].ts_ms:
                    idx[key] = bar
        self._index = idx

    def bar_at_minute(self, symbol: str, minute_ms: int) -> Bar | None:
        self._load()
        assert self._index is not None
        return self._index.get((symbol.upper(), minute_ms // 60_000 * 60_000))

    def next_bar_after(self, symbol: str, after_ms: int) -> Bar | None:
        self._load()
        assert self._index is not None
        sym = symbol.upper()
        keys = sorted(k for k in self._index if k[0] == sym and k[1] > after_ms)
        return self._index[keys[0]] if keys else None


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS book_a_signal_state ("
        "signal_id INTEGER PRIMARY KEY, status TEXT NOT NULL, "
        "skip_reason TEXT, trade_id INTEGER, updated_ms INTEGER NOT NULL)"
    )
    try:
        conn.execute("ALTER TABLE paper_cycles ADD COLUMN book TEXT NOT NULL DEFAULT 'B'")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def ensure_book_a_cycle(conn: sqlite3.Connection, capital: float = 100_000.0) -> int:
    _ensure_schema(conn)
    row = conn.execute("SELECT id FROM paper_cycles WHERE status='running' AND book='A' LIMIT 1").fetchone()
    if row:
        return int(row["id"])
    ms = int(datetime.now(tz=IST).timestamp() * 1000)
    cur = conn.execute(
        "INSERT INTO paper_cycles(started_ms, starting_wallet, wallet, peak_wallet, status, config_json, book) "
        "VALUES (?,?,?,?,?,?,?)",
        (ms, capital, capital, capital, "running", "{}", "A"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _wallet_a(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT wallet FROM paper_cycles WHERE status='running' AND book='A' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return float(row["wallet"]) if row else 100_000.0


def _margin_used(conn: sqlite3.Connection) -> float:
    used = 0.0
    for r in conn.execute("SELECT qty, entry_price FROM trades WHERE status='open' AND book='A'"):
        used += int(r["qty"]) * float(r["entry_price"]) * MIS_MARGIN_PCT / 100.0
    return used


def _signal_row_to_signal(r: sqlite3.Row) -> Signal:
    return Signal(
        ts_ms=int(r["ts_ms"]),
        symbol=r["symbol"],
        side=int(r["side"]),
        entry_ref=float(r["price"] or 0),
        stop=float(r["stop"] or 0),
        target=float(r["target"]) if r["target"] is not None else None,
        time_exit_ms=None,
        strategy=r["strategy"],
        book="A",
        role="pick",
    )


def _handled_ids(conn: sqlite3.Connection) -> set[int]:
    return {int(r["signal_id"]) for r in conn.execute("SELECT signal_id FROM book_a_signal_state")}


def _mark_signal(
    conn: sqlite3.Connection,
    signal_id: int,
    status: str,
    *,
    skip: str | None = None,
    trade_id: int | None = None,
) -> None:
    ms = int(datetime.now(tz=IST).timestamp() * 1000)
    conn.execute(
        "INSERT OR REPLACE INTO book_a_signal_state("
        "signal_id, status, skip_reason, trade_id, updated_ms) VALUES (?,?,?,?,?)",
        (signal_id, status, skip, trade_id, ms),
    )


def _close_trade(conn: sqlite3.Connection, tr: sqlite3.Row, px: float, ts_ms: int, reason: str) -> float:
    side = int(tr["side"])
    qty = int(tr["qty"])
    entry = float(tr["entry_price"])
    gross = (px - entry) * qty * side
    buy_v = entry * qty if side > 0 else px * qty
    sell_v = px * qty if side > 0 else entry * qty
    costs = round_trip(buy_v, sell_v, "MIS", rates_for("MIS")).total
    slip = (buy_v + sell_v) * 0.03 / 100.0
    net = gross - costs - slip
    risk = abs(entry - float(tr["stop_init"])) * qty
    r_mult = net / risk if risk else 0.0
    conn.execute(
        "UPDATE trades SET exit_ms=?, exit_price=?, exit_reason=?, gross_inr=?, costs_inr=?, "
        "net_inr=?, r_mult=?, status='closed' WHERE id=?",
        (ts_ms, px, reason, gross, costs + slip, net, r_mult, tr["id"]),
    )
    conn.execute(
        "UPDATE paper_cycles SET wallet = wallet + ?, peak_wallet = MAX(peak_wallet, wallet + ?) "
        "WHERE status='running' AND book='A'",
        (net, net),
    )
    return net


def job_book_a_minute(
    conn: sqlite3.Connection,
    source: MinuteBarSource,
    *,
    now_ms: int,
    tick_map: dict[str, float] | None = None,
) -> dict[str, Any]:
    """One minute of Book A paper: exits then new entries (idempotent per signal_id)."""
    mode = str(get_setting("book_a_mode", get_settings().book_a_mode)).lower()
    if mode != "paper":
        return {"mode": mode, "skipped": True}
    _ensure_schema(conn)
    ensure_book_a_cycle(conn)
    tick_map = tick_map or {}
    limits = limits_from_settings(get_settings())
    sq_at, no_entry = derive_engine_times(get_settings().broker_squareoff_at)
    no_entry = getattr(get_settings(), "no_entry_after", None) or no_entry
    ist = datetime.fromtimestamp(now_ms / 1000, tz=IST)
    hm = ist.hour * 60 + ist.minute
    no_parts = [int(x) for x in no_entry.split(":")]
    no_hm = no_parts[0] * 60 + no_parts[1]
    sq_parts = [int(x) for x in sq_at.split(":")]
    sq_hm = sq_parts[0] * 60 + sq_parts[1]
    minute_ms = now_ms // 60_000 * 60_000
    rules = ExitRules(
        product="MIS",
        slippage_pct=0.03,
        stop_extra_slip_pct=0.03,
        trail_atr_mult=2.5,
        max_sessions=500,
    )
    stats: dict[str, Any] = {"entries": 0, "exits": 0, "refusals": {}, "mode": "paper"}

    # Exits + square-off
    for tr in conn.execute("SELECT * FROM trades WHERE status='open' AND book='A'").fetchall():
        bar = source.bar_at_minute(tr["symbol"], minute_ms)
        if bar is None:
            continue
        pos = Position(
            symbol=tr["symbol"],
            strategy=tr["strategy"],
            book="A",
            side=int(tr["side"]),
            qty=int(tr["qty"]),
            entry_ms=int(tr["entry_ms"]),
            entry_price=float(tr["entry_price"]),
            stop_init=float(tr["stop_init"]),
            stop=float(tr["stop_now"] or tr["stop_init"]),
            risk_inr=abs(float(tr["entry_price"]) - float(tr["stop_init"])) * int(tr["qty"]),
            target=float(tr["target"]) if tr["target"] is not None else None,
        )
        sq_rules = rules
        sq_rules = replace(rules, square_off_ms=minute_ms) if hm >= sq_hm else rules
        pos, ev = step_exits(pos, bar, sq_rules, atr=None)
        if ev:
            _close_trade(conn, tr, ev.price, ev.ts_ms, ev.reason)
            stats["exits"] += 1
        else:
            conn.execute("UPDATE trades SET stop_now=? WHERE id=?", (pos.stop, tr["id"]))

    handled = _handled_ids(conn)
    open_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='open' AND book='A'").fetchone()["n"]
    open_syms = {r["symbol"] for r in conn.execute("SELECT symbol FROM trades WHERE status='open' AND book='A'")}

    if hm >= no_hm:
        conn.commit()
        return stats

    rows = conn.execute(
        "SELECT * FROM signals WHERE book='A' AND role='pick' AND ts_ms <= ? ORDER BY ts_ms, id",
        (now_ms,),
    ).fetchall()
    state = PortfolioState(capital=_wallet_a(conn), start_capital=100_000.0, open_intraday=int(open_n))
    state.open_symbols = set(open_syms)

    for r in rows:
        sid = int(r["id"])
        if sid in handled:
            continue
        sig = _signal_row_to_signal(r)
        nbar = source.next_bar_after(sig.symbol, sig.ts_ms)
        if nbar is None or nbar.ts_ms > now_ms:
            continue
        if now_ms - nbar.ts_ms > NO_BAR_MS:
            _mark_signal(conn, sid, "refused", skip="no_bar")
            stats["refusals"]["no_bar"] = stats["refusals"].get("no_bar", 0) + 1
            continue
        if nbar.ts_ms // 60_000 * 60_000 != minute_ms:
            continue
        if sig.symbol in open_syms:
            _mark_signal(conn, sid, "refused", skip="already_in_symbol")
            stats["refusals"]["already_in_symbol"] = stats["refusals"].get("already_in_symbol", 0) + 1
            continue
        if state.open_intraday >= limits.max_open_intraday:
            _mark_signal(conn, sid, "refused", skip="max_open_intraday")
            stats["refusals"]["max_open_intraday"] = stats["refusals"].get("max_open_intraday", 0) + 1
            continue
        ok, reason = can_open(state, sig, limits, now_ms)
        if not ok:
            _mark_signal(conn, sid, "refused", skip=reason)
            stats["refusals"][reason] = stats["refusals"].get(reason, 0) + 1
            continue
        fill = fill_entry_at_open(sig, nbar, rules)
        tick = tick_map.get(sig.symbol.upper(), 0.05)
        px = round_buy_limit(fill.price, tick) if sig.side > 0 else round_sell_limit(fill.price, tick)
        sz = size(px, sig.stop, _wallet_a(conn), limits.risk_per_trade_pct, tick, "A", limits)
        if sz.qty <= 0:
            _mark_signal(conn, sid, "refused", skip=sz.reason)
            stats["refusals"][sz.reason] = stats["refusals"].get(sz.reason, 0) + 1
            continue
        need_margin = sz.qty * px * MIS_MARGIN_PCT / 100.0
        free = _wallet_a(conn) - _margin_used(conn)
        if free + 1e-6 < need_margin:
            _mark_signal(conn, sid, "refused", skip="cash")
            stats["refusals"]["cash"] = stats["refusals"].get("cash", 0) + 1
            continue
        cur = conn.execute(
            "INSERT INTO trades(signal_id, symbol, book, strategy, side, qty, entry_ms, entry_price, "
            "stop_init, stop_now, target, mode, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                sig.symbol,
                "A",
                sig.strategy,
                sig.side,
                sz.qty,
                nbar.ts_ms,
                px,
                sig.stop,
                sig.stop,
                sig.target,
                "paper",
                "open",
            ),
        )
        tid = int(cur.lastrowid)
        _mark_signal(conn, sid, "filled", trade_id=tid)
        open_syms.add(sig.symbol)
        state.open_intraday += 1
        state.open_symbols.add(sig.symbol)
        stats["entries"] += 1
    conn.commit()
    return stats
