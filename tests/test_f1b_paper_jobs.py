"""F1b: paper jobs write DB rows and match lab/backtest over 30 fixture days."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")

from core.risk import RiskLimits
from core.types import Bar, Signal
from data.lake import Lake
from data.calendar import next_trading_day
from engine.paper_jobs import job_eod_fill, job_outcomes, job_scan
from engine.paper_engine import replay_through_jobs
from engine.state import init_db
from lab.backtest import run_daily_book
from strategies.base import Context


class _TinySwing:
    id = "T_swing"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars, ctx: Context) -> list[Signal]:  # noqa: ANN001
        closed = bars.closed()
        if len(closed) < 6 or len(closed) % 7 != 0:
            return []
        last = closed[-1]
        return [
            Signal(
                ts_ms=last.ts_ms,
                symbol=symbol,
                side=1,
                entry_ref=last.close * 1.005,
                stop=last.close * 0.97,
                target=None,
                time_exit_ms=None,
                strategy=self.id,
                book="B",
                role="pick",
                features={"atr14": last.close * 0.02},
            )
        ]


def _bar_ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST).timestamp() * 1000)


def _bars(n: int = 30, start: float = 100.0, dates: list[date] | None = None) -> list[Bar]:
    out: list[Bar] = []
    px = start
    dlist = dates or _trading_dates(date(2026, 1, 2), n)
    for i, d in enumerate(dlist[:n]):
        o = px
        c = px * (1.01 if i % 3 else 0.995)
        h = max(o, c) * 1.01
        lo = min(o, c) * 0.99
        out.append(Bar(ts_ms=_bar_ts(d), open=o, high=h, low=lo, close=c, volume=1000))
        px = c
    return out


def _write_lake(lake: Lake, symbol: str, bars: list[Bar], dates: list[date]) -> None:
    rows = []
    for b, d in zip(bars, dates, strict=True):
        rows.append(
            {
                "date": int(d.strftime("%Y%m%d")),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "delivery_qty": 0,
                "source": "test",
                "adj_factor": 1.0,
            }
        )
    lake.write_daily(symbol, pd.DataFrame(rows))
    lake.write_daily("NIFTYBEES", pd.DataFrame(rows))


def _trading_dates(start: date, n: int) -> list[date]:
    out: list[date] = []
    cur = start
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def test_thirty_day_paper_jobs_db_and_lab_parity(tmp_path):
    lake = Lake(tmp_path / "lake")
    dates = _trading_dates(date(2026, 1, 2), 30)
    bars = _bars(30, dates=dates)
    _write_lake(lake, "X", bars, dates)
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    lim = RiskLimits(max_open_swing=4, min_position_cnc_inr=20_000.0)
    strat = _TinySwing()
    import strategies.registry as reg

    reg.ALL[strat.id] = strat
    for td in dates:
        job_eod_fill(conn, lake, trade_date=td)
        job_scan(conn, lake, trade_date=td, enabled=[strat.id], symbols=["X"], write=True)
        job_outcomes(conn, lake, trade_date=td)
    # Fill pending created on the last scan day (next session bar).
    extra = next_trading_day(dates[-1])
    extra_bar = _bars(1, start=bars[-1].close, dates=[extra])[0]
    _write_lake(lake, "X", [extra_bar], [extra])
    job_eod_fill(conn, lake, trade_date=extra)
    n_sig = conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"]
    n_pend = conn.execute("SELECT COUNT(*) AS n FROM pending_orders").fetchone()["n"]
    n_tr = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
    assert n_sig > 0 and n_pend > 0 and n_tr > 0

    lab = run_daily_book(symbol="X", daily_bars=bars, strategy=strat, capital=100_000.0, limits=lim)
    rep = replay_through_jobs(symbol="X", daily_bars=bars, strategy=strat, capital=100_000.0, limits=lim)
    db_trades = conn.execute(
        "SELECT symbol, strategy, side, entry_ms, entry_price, qty FROM trades ORDER BY entry_ms"
    ).fetchall()

    def key_trade(t):  # noqa: ANN001
        return (t.symbol, t.strategy, t.side, t.entry_ms, round(t.entry_price, 4), t.qty)

    def key_db(r):  # noqa: ANN001
        return (r["symbol"], r["strategy"], r["side"], r["entry_ms"], round(r["entry_price"], 4), r["qty"])

    assert [key_trade(t) for t in rep.trades] == [key_trade(t) for t in lab.trades]
    # DB path matches replay for all fills that have a next-day bar in the lake (see extra eod above).
    assert len(db_trades) >= len(rep.trades) - 1
    assert [key_db(r) for r in db_trades] == [key_trade(t) for t in rep.trades[: len(db_trades)]]
