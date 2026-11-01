"""Mark price chain for portal equity (C19): quote → 1m recorder → daily lake."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from data.lake import Lake

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class MarkQuote:
    symbol: str
    mark: float
    mark_source: str  # quote | bar_1m | daily
    mark_age_s: float | None


def _quote_map(quotes: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for q in quotes.get("quotes") or []:
        sym = str(q.get("symbol") or "").upper()
        ltp = q.get("ltp")
        if sym and ltp is not None:
            out[sym] = float(ltp)
    return out


class _RecorderTail:
    """Per-file tail cache: last close per symbol from the newest lines only."""

    def __init__(self) -> None:
        self._mtime: float | None = None
        self._closes: dict[str, tuple[float, int]] = {}  # sym -> (close, ts_ms)
        self._path: Path | None = None

    def load(self, path: Path, *, tail_bytes: int = 512_000) -> None:
        if not path.exists():
            self._closes = {}
            self._mtime = None
            self._path = path
            return
        mtime = path.stat().st_mtime
        if self._path == path and self._mtime == mtime:
            return
        self._path = path
        self._mtime = mtime
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
            raw = f.read().decode("utf-8", errors="replace")
        closes: dict[str, tuple[float, int]] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = str(row.get("sym") or "").upper()
            c = row.get("c")
            if not sym or c is None:
                continue
            ts_ms = _row_ts_ms(row)
            prev = closes.get(sym)
            if prev is None or ts_ms >= prev[1]:
                closes[sym] = (float(c), ts_ms)
        self._closes = closes

    def close(self, symbol: str) -> tuple[float, int] | None:
        return self._closes.get(symbol.upper())


def _row_ts_ms(row: dict[str, Any]) -> int:
    ts = row.get("ts")
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return int(dt.timestamp() * 1000)
    if isinstance(ts, (int, float)):
        return int(ts)
    return 0


def _daily_close(lake: Lake | None, symbol: str) -> tuple[float, int] | None:
    if lake is None:
        return None
    df = lake.read_daily(symbol)
    if df.empty:
        return None
    row = df.iloc[-1]
    d = int(row["date"])
    y, m, day = d // 10000, (d // 100) % 100, d % 100
    ts_ms = int(datetime(y, m, day, 15, 30, tzinfo=IST).timestamp() * 1000)
    return float(row["close"]), ts_ms


def resolve_mark(
    symbol: str,
    *,
    quotes: dict[str, Any],
    data_dir: Path,
    lake: Lake | None,
    now_ms: int,
    trade_date: date | None = None,
    recorder: _RecorderTail | None = None,
) -> MarkQuote | None:
    sym = symbol.upper()
    qmap = _quote_map(quotes)
    if sym in qmap:
        qts = int(quotes.get("ts_ms") or now_ms)
        age = max(0.0, (now_ms - qts) / 1000.0)
        return MarkQuote(sym, qmap[sym], "quote", age)
    td = trade_date or datetime.fromtimestamp(now_ms / 1000, tz=IST).date()
    ymd = td.strftime("%Y%m%d")
    rec_path = data_dir / "ws" / f"bars_1m_{ymd}.jsonl"
    rec = recorder if recorder is not None else _RecorderTail()
    rec.load(rec_path)
    hit = rec.close(sym)
    if hit:
        px, ts_ms = hit
        return MarkQuote(sym, px, "bar_1m", max(0.0, (now_ms - ts_ms) / 1000.0))
    daily = _daily_close(lake, sym)
    if daily:
        px, ts_ms = daily
        return MarkQuote(sym, px, "daily", max(0.0, (now_ms - ts_ms) / 1000.0))
    return None


def build_marks(
    symbols: set[str],
    *,
    quotes: dict[str, Any],
    data_dir: Path,
    lake: Lake | None,
    now_ms: int,
) -> dict[str, MarkQuote]:
    rec = _RecorderTail()
    out: dict[str, MarkQuote] = {}
    for sym in symbols:
        mq = resolve_mark(sym, quotes=quotes, data_dir=data_dir, lake=lake, now_ms=now_ms, recorder=rec)
        if mq:
            out[sym] = mq
    return out
