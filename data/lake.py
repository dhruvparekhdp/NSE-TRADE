"""Parquet lake read/append/dedupe (plan A7.2 / P1)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BARS_1M = "bars_1m"
BARS_1D = "bars_1d"
SPREAD_1M = "spread_1m"


class Lake:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _daily_path(self, symbol: str) -> Path:
        d = self.root / BARS_1D
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{symbol}.parquet"

    def _minute_path(self, symbol: str, year: int, month: int) -> Path:
        d = self.root / BARS_1M / symbol
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{year:04d}-{month:02d}.parquet"

    def write_daily(self, symbol: str, df: pd.DataFrame) -> int:
        """Upsert daily bars; prefer ws/bhav over yf when deduping on date."""
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise ValueError(f"daily bars missing columns: {required - set(df.columns)}")
        path = self._daily_path(symbol)
        incoming = df.copy()
        if path.exists():
            old = pd.read_parquet(path)
            merged = pd.concat([old, incoming], ignore_index=True)
        else:
            merged = incoming
        # source priority: bhav > angel > yf > other
        prio = {"bhav": 3, "angel": 2, "ws": 2, "yf": 1}
        merged["_p"] = merged.get("source", pd.Series(["x"] * len(merged))).map(lambda s: prio.get(str(s), 0))
        merged = merged.sort_values(["date", "_p"]).drop_duplicates("date", keep="last")
        merged = merged.drop(columns=["_p"]).sort_values("date").reset_index(drop=True)
        merged.to_parquet(path, index=False)
        return len(merged)

    def read_daily(self, symbol: str) -> pd.DataFrame:
        path = self._daily_path(symbol)
        if not path.exists():
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "source"])
        return pd.read_parquet(path)

    def write_minutes(self, symbol: str, df: pd.DataFrame) -> int:
        required = {"ts_ms", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise ValueError(f"1m bars missing columns: {required - set(df.columns)}")
        if df.empty:
            return 0
        work = df.copy()
        work["ts"] = pd.to_datetime(work["ts_ms"], unit="ms", utc=True)
        written = 0
        for (y, m), part in work.groupby([work["ts"].dt.year, work["ts"].dt.month]):
            path = self._minute_path(symbol, int(y), int(m))
            part = part.drop(columns=["ts"])
            if path.exists():
                old = pd.read_parquet(path)
                merged = pd.concat([old, part], ignore_index=True)
            else:
                merged = part
            prio = {"ws": 2, "hist": 1, "angel": 1}
            if "source" not in merged.columns:
                merged["source"] = "hist"
            merged["_p"] = merged["source"].map(lambda s: prio.get(str(s), 0))
            merged = merged.sort_values(["ts_ms", "_p"]).drop_duplicates("ts_ms", keep="last")
            merged = merged.drop(columns=["_p"]).sort_values("ts_ms").reset_index(drop=True)
            merged.to_parquet(path, index=False)
            written += len(part)
        return written

    def read_minutes(self, symbol: str, start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
        root = self.root / BARS_1M / symbol
        if not root.exists():
            return pd.DataFrame(columns=["ts_ms", "open", "high", "low", "close", "volume", "source"])
        frames = [pd.read_parquet(p) for p in sorted(root.glob("*.parquet"))]
        if not frames:
            return pd.DataFrame(columns=["ts_ms", "open", "high", "low", "close", "volume", "source"])
        df = pd.concat(frames, ignore_index=True).sort_values("ts_ms")
        if start_ms is not None:
            df = df[df["ts_ms"] >= start_ms]
        if end_ms is not None:
            df = df[df["ts_ms"] <= end_ms]
        return df.reset_index(drop=True)
