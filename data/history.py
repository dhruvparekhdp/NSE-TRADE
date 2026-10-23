"""Historical loaders: NSE bhavcopy + Angel candles (injectable client; tests use fixtures)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from data.lake import Lake


class CandleClient(Protocol):
    def get_candles(
        self, token: str, interval: str, from_dt: datetime, to_dt: datetime
    ) -> list[list[Any]]: ...


def _is_udiff(fieldnames: list[str] | None) -> bool:
    if not fieldnames:
        return False
    upper = {f.upper() for f in fieldnames}
    return "TCKRSYMB" in upper or "TRADDT" in upper


def parse_bhavcopy_udiff(text: str) -> pd.DataFrame:
    """NSE UDiFF daily bhav (Jul 2024+) — TckrSymb, TradDt, OpnPric, HghPric, LwPric, ClsPric, TotTradgVol."""
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        lower_map = {rk.lower(): (rv or "").strip() for rk, rv in row.items()}

        def g(*keys: str, _m: dict[str, str] = lower_map) -> str:
            for k in keys:
                if k.lower() in _m:
                    return _m[k.lower()]
            return ""

        series = g("SctySrs", "SERIES", "Series").upper() or "EQ"
        if series != "EQ":
            continue
        sym = g("TckrSymb", "SYMBOL", "Symbol").upper()
        if not sym:
            continue
        d = _parse_bhav_date(g("TradDt", "TIMESTAMP", "DATE1", "Date"))
        rows.append(
            {
                "symbol": sym,
                "date": int(d.strftime("%Y%m%d")),
                "open": float(g("OpnPric", "OPEN", "Open") or 0),
                "high": float(g("HghPric", "HIGH", "High") or 0),
                "low": float(g("LwPric", "LOW", "Low") or 0),
                "close": float(g("ClsPric", "CLOSE", "Close") or 0),
                "volume": int(float(g("TotTradgVol", "TOTTRDQTY", "TTL_TRD_QNTY", "Volume") or 0)),
                "delivery_qty": int(float(g("DlvryQty", "DELIV_QTY") or 0) or 0),
                "source": "bhav_udiff",
                "adj_factor": 1.0,
            }
        )
    return pd.DataFrame(rows)


def parse_bhavcopy_csv(text: str) -> pd.DataFrame:
    """Auto-detect UDiFF vs classic NSE bhavcopy CSV."""
    sample = io.StringIO(text)
    reader = csv.DictReader(sample)
    if _is_udiff(reader.fieldnames):
        return parse_bhavcopy_udiff(text)
    sample.seek(0)
    reader = csv.DictReader(sample)
    rows = []
    for row in reader:
        sym = (row.get("SYMBOL") or row.get("Symbol") or "").strip().upper()
        series = (row.get("SERIES") or row.get("Series") or "EQ").strip().upper()
        if series and series != "EQ":
            continue
        if not sym:
            continue
        ts = row.get("TIMESTAMP") or row.get("DATE1") or row.get("Date") or ""
        d = _parse_bhav_date(ts)
        rows.append(
            {
                "symbol": sym,
                "date": int(d.strftime("%Y%m%d")),
                "open": float(row.get("OPEN") or row.get("Open") or 0),
                "high": float(row.get("HIGH") or row.get("High") or 0),
                "low": float(row.get("LOW") or row.get("Low") or 0),
                "close": float(row.get("CLOSE") or row.get("Close") or 0),
                "volume": int(float(row.get("TOTTRDQTY") or row.get("TTL_TRD_QNTY") or row.get("Volume") or 0)),
                "delivery_qty": int(float(row.get("DELIV_QTY") or 0) or 0),
                "source": "bhav",
                "adj_factor": 1.0,
            }
        )
    return pd.DataFrame(rows)


def parse_bhavcopy_zip(data: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("no csv in bhavcopy zip")
        text = zf.read(names[0]).decode("utf-8", errors="replace")
    return parse_bhavcopy_csv(text)


def _parse_bhav_date(s: str) -> date:
    s = s.strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # already YYYYMMDD
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    raise ValueError(f"bad bhav date: {s!r}")


def ingest_bhav_to_lake(lake: Lake, df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    if df.empty:
        return counts
    for sym, part in df.groupby("symbol"):
        cols = ["date", "open", "high", "low", "close", "volume", "delivery_qty", "source"]
        counts[str(sym)] = lake.write_daily(str(sym), part[cols])
    return counts


def angel_candles_to_df(rows: list[list[Any]], source: str = "angel") -> pd.DataFrame:
    """SmartAPI candle rows: [timestamp, open, high, low, close, volume]."""
    out = []
    for r in rows:
        ts = r[0]
        if isinstance(ts, str):
            # "2024-01-02T09:15:00+05:30" or similar
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_ms = int(dt.timestamp() * 1000)
        else:
            ts_ms = int(ts)
        out.append(
            {
                "ts_ms": ts_ms,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": int(float(r[5])) if len(r) > 5 else 0,
                "n_ticks": 0,
                "source": source,
            }
        )
    return pd.DataFrame(out)


def backfill_minutes(
    lake: Lake,
    client: CandleClient,
    *,
    symbol: str,
    token: str,
    windows: list[tuple[datetime, datetime]],
    state_path: Path | None = None,
) -> int:
    """Resumable windowed backfill. State JSON tracks last completed window index."""
    import json

    start_i = 0
    if state_path and state_path.exists():
        start_i = int(json.loads(state_path.read_text()).get("next_i", 0))
    total = 0
    for i, (frm, to) in enumerate(windows):
        if i < start_i:
            continue
        rows = client.get_candles(token, "ONE_MINUTE", frm, to)
        if rows:
            df = angel_candles_to_df(rows)
            lake.write_minutes(symbol, df)
            total += len(df)
        if state_path:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({"next_i": i + 1, "symbol": symbol}))
    return total


def window_30d(start: date, end: date) -> list[tuple[datetime, datetime]]:
    """Walk backwards? Plan: walk back in 30-day windows. Forward is fine for tests."""
    from datetime import timedelta

    out = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=29), end)
        out.append(
            (
                datetime(cur.year, cur.month, cur.day, 9, 15),
                datetime(nxt.year, nxt.month, nxt.day, 15, 30),
            )
        )
        cur = nxt + timedelta(days=1)
    return out
