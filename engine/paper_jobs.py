"""Book B paper jobs: scan, fill, outcomes (V-FIX-2 F1b)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import get_setting, get_settings
from core.exits import ExitRules, Position, fill_entry, step_exits, virtual_outcome
from core.indicators import atr as atr_series
from core.risk import PortfolioState, can_open, limits_from_settings, on_swing_close, on_swing_open, size
from core.sessions import daily_bar_close_ms
from core.types import Bar, Signal
from data.calendar import next_trading_day
from data.lake import Lake
from data.sectors import load_sector_map
from engine.jobs import load_pending_signals, persist_pending, persist_signals
from engine.paper_engine import scan_book_b_day
from lab.market_filters import f1_skip_reason, f2_skip_reason
from strategies.base import Context, Strategy
from strategies.registry import ALL
from strategies.swing_breakout import bars_from_daily_df

IST = ZoneInfo("Asia/Kolkata")


def _date_to_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST).timestamp() * 1000)


def _sessions_held(entry_ms: int, trade_date: date) -> int:
    entry_d = datetime.fromtimestamp(entry_ms / 1000, tz=IST).date()
    n = 0
    cur = entry_d
    while cur < trade_date:
        cur = next_trading_day(cur)
        n += 1
    return n


def daily_bars_upto(lake: Lake, symbol: str, end: date) -> list[Bar]:
    df = lake.read_daily(symbol)
    if df.empty:
        return []
    end_int = int(end.strftime("%Y%m%d"))
    part = df[df["date"] <= end_int]
    return bars_from_daily_df(part.to_dict(orient="records"))


def nifty_closes(lake: Lake, end: date) -> list[float]:
    for sym in ("NIFTYBEES", "NIFTY", "RELIANCE"):
        bars = daily_bars_upto(lake, sym, end)
        if bars:
            return [b.close for b in bars]
    return []


def load_portfolio_state(conn: sqlite3.Connection, *, capital: float = 100_000.0) -> PortfolioState:
    """Open holdings plus pending CNC orders both reserve swing slots (C17.1)."""
    state = PortfolioState(capital=capital, start_capital=capital)
    sector_map = load_sector_map() or None
    for row in conn.execute("SELECT symbol, qty FROM holdings WHERE qty > 0"):
        sym = str(row["symbol"]).upper()
        state.open_symbols.add(sym)
        state.open_swing += 1
        on_swing_open(state, sym, sector_map)
    for row in conn.execute("SELECT symbol FROM pending_orders WHERE status='pending'"):
        sym = str(row["symbol"]).upper()
        if sym in state.open_symbols:
            continue
        state.open_symbols.add(sym)
        state.open_swing += 1
        on_swing_open(state, sym, sector_map)
    return state


def _reserve_swing_slot(state: PortfolioState, symbol: str, sector_map: dict[str, str] | None) -> None:
    sym = symbol.upper()
    if sym in (state.open_symbols or set()):
        return
    state.open_symbols.add(sym)
    state.open_swing += 1
    on_swing_open(state, sym, sector_map)


def market_filter_mode() -> str:
    """on (PREREG F1/F2) | off (paper compare) | shadow (log only). C13."""
    return str(get_setting("market_filter", "on")).lower()


def f1_f2_reasons(closes_nifty: list[float]) -> tuple[str | None, str | None]:
    if len(closes_nifty) < 273:
        return None, None
    f1 = f1_skip_reason(closes_nifty)
    f2 = f2_skip_reason(closes_nifty) if not f1 else None
    return f1, f2


def daily_bars_ready(
    lake: Lake,
    trade_date: date,
    probes: tuple[str, ...] = ("NIFTYBEES", "SBIN", "RELIANCE"),
) -> bool:
    """False until today's daily bar is in the lake (C17.4 — fill/scan after job_daily_bars)."""
    for sym in probes:
        bars = daily_bars_upto(lake, sym, trade_date)
        if not bars:
            continue
        bar_d = datetime.fromtimestamp(bars[-1].ts_ms / 1000, tz=IST).date()
        if bar_d == trade_date:
            return True
    return False


def _cnc_buy_cash_needed(buy_value: float, slippage_pct: float = 0.05) -> float:
    from core.costs import order_brokerage, rates_for

    rates = rates_for("CNC")
    brok = order_brokerage(buy_value, rates)
    stt = buy_value * rates.stt_buy_pct / 100.0
    exchange = buy_value * rates.exchange_pct / 100.0
    sebi = buy_value * rates.sebi_pct / 100.0
    stamp = buy_value * rates.stamp_buy_pct / 100.0
    gst = (brok + exchange + sebi) * rates.gst_pct / 100.0
    slip = buy_value * slippage_pct / 100.0
    return round(buy_value + brok + stt + exchange + sebi + stamp + gst + slip + 1e-9, 2)


def _cnc_sell_cash_credit(sell_value: float, slippage_pct: float = 0.05) -> float:
    from core.costs import order_brokerage, rates_for

    rates = rates_for("CNC")
    brok = order_brokerage(sell_value, rates)
    stt = sell_value * rates.stt_sell_pct / 100.0
    exchange = sell_value * rates.exchange_pct / 100.0
    sebi = sell_value * rates.sebi_pct / 100.0
    gst = (brok + exchange + sebi) * rates.gst_pct / 100.0
    dp = rates.dp_inr * (1.0 + rates.dp_gst_pct / 100.0) if rates.dp_inr else 0.0
    slip = sell_value * slippage_pct / 100.0
    return round(sell_value - (brok + stt + exchange + sebi + gst + dp + slip) + 1e-9, 2)


def ensure_paper_cycle(conn: sqlite3.Connection, capital: float = 100_000.0) -> None:
    row = conn.execute("SELECT id FROM paper_cycles WHERE status='running' LIMIT 1").fetchone()
    if row:
        return
    ms = int(datetime.now(tz=IST).timestamp() * 1000)
    conn.execute(
        "INSERT INTO paper_cycles(started_ms, starting_wallet, wallet, peak_wallet, status, config_json) "
        "VALUES (?,?,?,?,?,?)",
        (ms, capital, capital, capital, "running", "{}"),
    )
    conn.commit()


def _wallet(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT wallet FROM paper_cycles WHERE status='running' ORDER BY id DESC LIMIT 1").fetchone()
    return float(row["wallet"]) if row else 100_000.0


def _bump_wallet(conn: sqlite3.Connection, delta: float) -> None:
    conn.execute(
        "UPDATE paper_cycles SET wallet = wallet + ?, peak_wallet = MAX(peak_wallet, wallet + ?) "
        "WHERE status='running'",
        (delta, delta),
    )
    conn.commit()


def strategies_for_scan(enabled: list[str] | None) -> list[Strategy]:
    enabled = enabled or []
    if not enabled:
        return [s for s in ALL.values() if s.book == "B"]
    return [ALL[sid] for sid in enabled if sid in ALL and ALL[sid].book == "B"]


def job_scan(
    conn: sqlite3.Connection,
    lake: Lake,
    *,
    trade_date: date,
    enabled: list[str] | None = None,
    symbols: list[str] | None = None,
    write: bool = True,
) -> list[dict[str, Any]]:
    """16:20 scan on closed daily bars; market_filter controls F1/F2 (C13)."""
    syms = symbols or [r[0] for r in conn.execute("SELECT symbol FROM instruments WHERE in_universe=1").fetchall()]
    if not syms:
        syms = symbols or []
    bar_probes = tuple(dict.fromkeys([*syms, "NIFTYBEES", "SBIN", "RELIANCE"]))
    if not daily_bars_ready(lake, trade_date, bar_probes):
        return []
    settings = get_settings()
    limits = limits_from_settings(settings)
    sector_map = load_sector_map() or None
    state = load_portfolio_state(conn, capital=_wallet(conn))
    closes_nifty = nifty_closes(lake, trade_date)
    next_td = next_trading_day(trade_date)
    next_iso = next_td.isoformat()
    scan_iso = trade_date.isoformat()
    mf = market_filter_mode()
    filter_on = mf == "on"
    filter_off = mf == "off"
    filter_shadow = mf == "shadow"
    out: list[dict[str, Any]] = []

    f1, f2 = f1_f2_reasons(closes_nifty)

    for sym in syms:
        bars = daily_bars_upto(lake, sym, trade_date)
        if len(bars) < 2:
            continue
        bar = bars[-1]
        decision_ms = daily_bar_close_ms(bar.ts_ms) + 1_000
        ctx = Context(trade_date=scan_iso)

        for strat in strategies_for_scan(enabled):
            sigs = scan_book_b_day(
                symbol=sym,
                daily_bars=bars,
                strategy=strat,
                state=state,
                limits=limits,
                decision_ms=decision_ms,
                ctx=ctx,
            )
            for sig in sigs:
                decision = "shadow" if not (enabled or []) or filter_shadow else "logged"
                skip = None
                would_skip: str | None = None
                if filter_on and f1:
                    would_skip = f1
                elif filter_on and f2:
                    would_skip = f2
                elif filter_off and f1:
                    would_skip = f1
                elif filter_off and f2:
                    would_skip = f2

                if sig.role == "pick":
                    if filter_shadow:
                        skip = would_skip or "market_filter_shadow"
                        decision = "shadow"
                    elif filter_on and would_skip:
                        skip = would_skip
                    else:
                        sym_up = sym.upper()
                        if sym_up in (state.open_symbols or set()):
                            skip = "already_in_symbol"
                        else:
                            ok, reason = can_open(state, sig, limits, decision_ms, sector_map=sector_map)
                            if not ok:
                                skip = "already_in_symbol" if reason == "symbol_open" else reason
                            else:
                                sz = size(
                                    sig.entry_ref,
                                    sig.stop,
                                    state.capital,
                                    limits.risk_per_trade_pct,
                                    0.05,
                                    "B",
                                    limits,
                                )
                                if sz.qty <= 0:
                                    skip = sz.reason
                                elif write and not filter_shadow:
                                    persist_pending(
                                        conn,
                                        trade_date=next_iso,
                                        symbol=sym,
                                        strategy=sig.strategy,
                                        side=sig.side,
                                        qty=sz.qty,
                                        limit_price=sig.entry_ref,
                                        stop=sig.stop,
                                        target=sig.target,
                                        created_ms=decision_ms,
                                    )
                                    decision = "pending"
                                    _reserve_swing_slot(state, sym, sector_map)
                feat = {**(sig.features or {}), "decision": decision, "skip_reason": skip}
                if would_skip and filter_off and sig.role == "pick" and decision == "pending":
                    feat["would_skip_reason"] = would_skip
                sig.features = feat
                row = {
                    "trade_date": scan_iso,
                    "symbol": sym,
                    "strategy": sig.strategy,
                    "role": sig.role,
                    "decision": decision,
                    "skip_reason": skip,
                    "would_skip_reason": feat.get("would_skip_reason"),
                }
                out.append(row)
            if write and sigs:
                persist_signals(conn, sigs, scan_iso)
    return out


def _close_open_trade(conn: sqlite3.Connection, tr_id: int, sym: str, px: float, ts_ms: int, reason: str) -> float:
    row = conn.execute("SELECT * FROM trades WHERE id=?", (tr_id,)).fetchone()
    if row is None:
        return 0.0
    side = int(row["side"])
    qty = int(row["qty"])
    entry = float(row["entry_price"])
    gross = (px - entry) * qty * side
    from core.costs import rates_for, round_trip

    buy_v = entry * qty if side > 0 else px * qty
    sell_v = px * qty if side > 0 else entry * qty
    costs = round_trip(buy_v, sell_v, "CNC", rates_for("CNC")).total
    slip = (buy_v + sell_v) * 0.05 / 100.0
    net = gross - costs - slip
    conn.execute(
        "UPDATE trades SET exit_ms=?, exit_price=?, exit_reason=?, gross_inr=?, costs_inr=?, net_inr=?, "
        "status='closed' WHERE id=?",
        (ts_ms, px, reason, gross, costs + slip, net, tr_id),
    )
    conn.execute("DELETE FROM holdings WHERE symbol=?", (sym,))
    sector_map = load_sector_map() or None
    st = load_portfolio_state(conn)
    on_swing_close(st, sym, sector_map)
    sell_v = px * qty
    _bump_wallet(conn, _cnc_sell_cash_credit(sell_v))
    return net


def job_eod_fill(
    conn: sqlite3.Connection,
    lake: Lake,
    *,
    trade_date: date,
) -> list[dict[str, Any]]:
    """16:15 manage open CNC positions and fill pending entries on today's bar."""
    if not daily_bars_ready(lake, trade_date, ("NIFTYBEES", "SBIN", "RELIANCE")):
        return []
    ensure_paper_cycle(conn)
    iso = trade_date.isoformat()
    pending = load_pending_signals(conn, iso)
    rules = ExitRules(
        product="CNC",
        entry_limit_offset_pct=0.0,
        slippage_pct=0.05,
        stop_extra_slip_pct=0.05,
        trail_atr_mult=2.5,
        max_sessions=20,
    )
    results: list[dict[str, Any]] = []
    settings = get_settings()
    mode = settings.mode

    open_rows = conn.execute("SELECT * FROM trades WHERE status='open' AND book='B'").fetchall()
    for row in open_rows:
        sym = row["symbol"]
        bars = daily_bars_upto(lake, sym, trade_date)
        if not bars:
            continue
        bar = bars[-1]
        pos = Position(
            symbol=sym,
            strategy=row["strategy"],
            book="B",
            side=int(row["side"]),
            qty=int(row["qty"]),
            entry_ms=int(row["entry_ms"]),
            entry_price=float(row["entry_price"]),
            stop_init=float(row["stop_init"]),
            stop=float(row["stop_now"] or row["stop_init"]),
            risk_inr=abs(float(row["entry_price"]) - float(row["stop_init"])) * int(row["qty"]),
            target=row["target"],
            sessions_held=_sessions_held(int(row["entry_ms"]), trade_date),
        )
        hs = [b.high for b in bars]
        ls = [b.low for b in bars]
        cs = [b.close for b in bars]
        atr14 = atr_series(hs, ls, cs, 14)[-1]
        atr_f = float(atr14) if atr14 is not None else None
        pos, ev = step_exits(pos, bar, rules, atr=atr_f)
        if ev:
            _close_open_trade(conn, int(row["id"]), sym, ev.price, ev.ts_ms, ev.reason)
            results.append({"symbol": sym, "status": "closed", "reason": ev.reason})
        else:
            conn.execute("UPDATE trades SET stop_now=? WHERE id=?", (pos.stop, row["id"]))

    for sig in pending:
        bars = daily_bars_upto(lake, sig.symbol, trade_date)
        if not bars:
            results.append({"symbol": sig.symbol, "status": "no_bar"})
            continue
        bar = bars[-1]
        fill = fill_entry(sig, bar, rules)
        if fill is None:
            conn.execute(
                "UPDATE pending_orders SET status='no_fill' WHERE trade_date=? AND symbol=? AND status='pending'",
                (iso, sig.symbol),
            )
            results.append({"symbol": sig.symbol, "status": "no_fill"})
            continue
        limits = limits_from_settings(settings)
        sz = size(fill.price, sig.stop, _wallet(conn), limits.risk_per_trade_pct, 0.05, "B", limits)
        if sz.qty <= 0:
            results.append({"symbol": sig.symbol, "status": sz.reason})
            continue
        buy_v = fill.price * sz.qty
        need = _cnc_buy_cash_needed(buy_v)
        if _wallet(conn) + 1e-6 < need:
            conn.execute(
                "UPDATE pending_orders SET status='no_fill' WHERE trade_date=? AND symbol=? AND status='pending'",
                (iso, sig.symbol),
            )
            results.append({"symbol": sig.symbol, "status": "cash", "reason": "cash"})
            continue
        ms = fill.ts_ms
        _bump_wallet(conn, -need)
        conn.execute(
            "INSERT INTO trades(signal_id, symbol, book, strategy, side, qty, entry_ms, entry_price, "
            "stop_init, stop_now, target, mode, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                None,
                sig.symbol,
                "B",
                sig.strategy,
                sig.side,
                sz.qty,
                ms,
                fill.price,
                sig.stop,
                sig.stop,
                sig.target,
                mode,
                "open",
            ),
        )
        conn.execute(
            "INSERT INTO holdings(symbol, qty, avg_price, bought_ms) VALUES (?,?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET qty=qty+excluded.qty, avg_price=excluded.avg_price",
            (sig.symbol, sz.qty, fill.price, ms),
        )
        conn.execute(
            "UPDATE pending_orders SET status='filled' WHERE trade_date=? AND symbol=? AND status='pending'",
            (iso, sig.symbol),
        )
        sector_map = load_sector_map() or None
        st = load_portfolio_state(conn)
        on_swing_open(st, sig.symbol, sector_map)
        results.append({"symbol": sig.symbol, "status": "filled", "qty": sz.qty, "price": fill.price})
    conn.commit()
    return results


def job_outcomes(
    conn: sqlite3.Connection,
    lake: Lake,
    *,
    trade_date: date,
) -> int:
    """16:30 virtual outcomes for every signal on trade_date."""
    iso = trade_date.isoformat()
    rows = conn.execute("SELECT * FROM signals WHERE trade_date=?", (iso,)).fetchall()
    rules = ExitRules(product="CNC", entry_limit_offset_pct=0.0)
    n = 0
    for r in rows:
        sym = r["symbol"]
        bars = daily_bars_upto(lake, sym, trade_date)
        if len(bars) < 2:
            continue
        sig = Signal(
            ts_ms=int(r["ts_ms"]),
            symbol=sym,
            side=int(r["side"]),
            entry_ref=float(r["price"] or 0),
            stop=float(r["stop"] or 0),
            target=r["target"],
            time_exit_ms=None,
            strategy=r["strategy"],
            book=r["book"],
            role=r["role"],
        )
        outcome = virtual_outcome(sig, bars[-2:], rules)
        conn.execute(
            "INSERT INTO events(ts_ms, kind, json) VALUES (?,?,?)",
            (
                int(datetime.now(tz=IST).timestamp() * 1000),
                "signal_outcome",
                json.dumps({"signal_id": r["id"], "role": r["role"], **outcome}),
            ),
        )
        n += 1
    conn.commit()
    return n


def job_pending(conn: sqlite3.Connection, *, trade_date: date) -> int:
    iso = trade_date.isoformat()
    return int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM pending_orders WHERE trade_date=? AND status='pending'",
            (iso,),
        ).fetchone()["n"]
    )


def run_paper_day(
    conn: sqlite3.Connection,
    lake: Lake,
    *,
    trade_date: date,
    enabled: list[str] | None,
    symbols: list[str],
) -> None:
    """One trading day: fill → scan (test helper)."""
    job_eod_fill(conn, lake, trade_date=trade_date)
    job_scan(conn, lake, trade_date=trade_date, enabled=enabled, symbols=symbols, write=True)
    job_outcomes(conn, lake, trade_date=trade_date)
