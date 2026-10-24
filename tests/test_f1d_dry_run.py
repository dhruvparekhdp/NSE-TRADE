"""F1d: paper_dry_run prints decisions without persisting."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from core.types import Signal
from data.lake import Lake
from engine.state import init_db
from strategies.base import Context

IST = ZoneInfo("Asia/Kolkata")


class _TinySwing:
    id = "T_swing"
    book = "B"
    timeframe = "1d"

    def on_bar(self, symbol: str, bars, ctx: Context) -> list[Signal]:  # noqa: ANN001
        closed = bars.closed()
        if len(closed) < 6:
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
            )
        ]


def test_dry_run_no_write(tmp_path, capsys):
    import strategies.registry as reg
    from scripts import paper_dry_run

    reg.ALL["T_swing"] = _TinySwing()
    lake = Lake(tmp_path / "lake")
    rows = []
    d0 = date(2026, 1, 2)
    px = 100.0
    for i in range(8):
        d = d0.toordinal() + i
        dt = date.fromordinal(d)
        if dt.weekday() >= 5:
            continue
        ts = int(datetime(dt.year, dt.month, dt.day, 9, 15, tzinfo=IST).timestamp() * 1000)
        o = px
        c = px * 1.02
        rows.append(
            {
                "date": int(dt.strftime("%Y%m%d")),
                "open": o,
                "high": c * 1.01,
                "low": o * 0.99,
                "close": c,
                "volume": 1,
                "source": "t",
                "adj_factor": 1.0,
            }
        )
        lake.write_daily("X", pd.DataFrame([rows[-1]]))
        px = c
        _ = ts
    conn = init_db(tmp_path / "e.db")
    conn.execute(
        "INSERT INTO instruments(symbol, token, tick_size, lot_size, in_universe, updated_ms) VALUES (?,?,?,?,?,?)",
        ("X", "1", 0.05, 1, 1, 1),
    )
    conn.commit()
    conn.close()
    d_int = int(rows[-1]["date"])
    scan_day = date(d_int // 10000, (d_int // 100) % 100, d_int % 100)
    paper_dry_run.main(
        ["--date", scan_day.isoformat(), "--lake", str(tmp_path / "lake"), "--no-write", "--symbols", "X"]
    )
    out = capsys.readouterr().out
    assert "decision=" in out
