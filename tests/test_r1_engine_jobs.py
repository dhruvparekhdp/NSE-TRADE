"""R1: runner jobs write tables; 08:45 brief; 30-day job replay == lab/backtest."""

from __future__ import annotations

from core.risk import RiskLimits
from core.types import Bar, Signal
from engine.jobs import job_morning_brief, job_opening_scorecard, job_preopen
from engine.paper_engine import replay_through_jobs
from engine.state import init_db
from lab.backtest import run_daily_book
from strategies.base import Context


class _TinySwing:
    """Fires once after 5 bars so a 30-day fixture produces trades."""

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


def _bars(n: int = 30, start: float = 100.0) -> list[Bar]:
    out: list[Bar] = []
    px = start
    for i in range(n):
        o = px
        c = px * (1.01 if i % 3 else 0.995)
        h = max(o, c) * 1.01
        lo = min(o, c) * 0.99
        out.append(Bar(ts_ms=1_700_000_000_000 + i * 86_400_000, open=o, high=h, low=lo, close=c, volume=1000))
        px = c
    return out


def test_morning_brief_fills_table(tmp_path):
    conn = init_db(tmp_path / "e.db")
    now = 1_700_000_000_000
    conn.execute(
        "INSERT INTO global_cues(ts_ms, key, last, chg_pct, ref_close, source, stale, mkt_ts_ms) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (now, "SPX", 5000.0, 0.5, 4975.0, "yahoo", 0, now),
    )
    conn.execute(
        "INSERT INTO flows(trade_date, fii_net_cr, dii_net_cr, source, final) VALUES (?,?,?,?,?)",
        ("2023-11-14", -100.0, 200.0, "nse", 1),
    )
    conn.execute(
        "INSERT INTO headlines(ts_ms, source, title, event_type, score) VALUES (?,?,?,?,?)",
        (now, "test", "Sample headline", "macro", 0.1),
    )
    conn.commit()
    brief = job_morning_brief(conn, now_ms=now)
    row = conn.execute("SELECT trade_date, json FROM morning_brief").fetchone()
    assert row is not None
    assert brief["trade_date"] == row["trade_date"]
    assert "Sample headline" in row["json"]
    assert "-100" in row["json"] or "-100.0" in row["json"]


def test_preopen_job_writes_with_fake_nse(tmp_path):
    conn = init_db(tmp_path / "e.db")

    def fake_get(url: str):
        return {
            "data": [
                {
                    "symbol": "NIFTY",
                    "iep": 25000.0,
                    "previousClose": 24800.0,
                    "totalBuyQuantity": 100,
                    "totalSellQuantity": 80,
                }
            ]
        }

    n = job_preopen(conn, now_ms=1_700_000_000_000, get_json=fake_get, final=True)
    assert n >= 1
    row = conn.execute("SELECT symbol, final FROM preopen_snapshots").fetchone()
    assert row["symbol"] == "NIFTY" and row["final"] == 1


def test_opening_scorecard_finalizes_type(tmp_path):
    conn = init_db(tmp_path / "e.db")
    job_opening_scorecard(
        conn,
        trade_date="2026-10-23",
        open_px=100.0,
        prev_close=99.0,
        last_px=101.0,
        finalize_type=True,
    )
    row = conn.execute("SELECT open_type, gap_pct FROM opening_summary").fetchone()
    assert row["open_type"] == "gap-up-and-go"
    assert row["gap_pct"] > 0


def test_thirty_day_jobs_match_lab_backtest():
    bars = _bars(30)
    strat = _TinySwing()
    lim = RiskLimits(max_open_swing=4, min_position_cnc_inr=20_000.0)
    lab = run_daily_book(symbol="X", daily_bars=bars, strategy=strat, capital=100_000.0, limits=lim)
    paper = replay_through_jobs(symbol="X", daily_bars=bars, strategy=strat, capital=100_000.0, limits=lim)

    def key(t):  # noqa: ANN001
        return (t.symbol, t.strategy, t.side, t.entry_ms, round(t.entry_price, 4), t.qty)

    assert [key(t) for t in paper.trades] == [key(t) for t in lab.trades]


def test_runner_registers_r1_jobs():
    from engine.runner import EngineRunner

    r = EngineRunner.__new__(EngineRunner)
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    r.settings = type(
        "S",
        (),
        {
            "broker_squareoff_at": "15:10",
            "square_off_at": "14:55",
            "no_entry_after": "14:35",
            "strategies_enabled": [],
        },
    )()
    r.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    r._schedule()
    ids = {j.id for j in r.scheduler.get_jobs()}
    for need in (
        "morning_brief",
        "cues",
        "preopen",
        "flows",
        "pending",
        "eod_fill",
        "scan",
        "outcomes",
        "eod_report",
        "bhav_check",
        "book_a_shadow",
        "open_type",
    ):
        assert need in ids, need
