"""Free / low-cost live quotes — prefer these over Angel for watching & paper.

Primary: Yahoo Finance chart API (query1) — free, delayed for NSE (.NS).
No reliable free NSE tick websocket; polling is the free path.
Angel SmartAPI reserved for login/orders when you go live.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
_UA = "Mozilla/5.0 (compatible; nse-engine/0.1; +https://localhost)"


@dataclass(frozen=True)
class Quote:
    symbol: str
    ltp: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: int | None = None
    source: str = "yahoo"
    ts_ms: int = 0


def yf_symbol(nse_symbol: str) -> str:
    s = nse_symbol.upper().strip()
    if s.endswith(".NS"):
        return s
    return f"{s}.NS"


def _http_json(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_one_yahoo(nse_symbol: str) -> Quote | None:
    sym = nse_symbol.upper().strip()
    url = YAHOO_CHART.format(symbol=urllib.parse.quote(yf_symbol(sym)))
    try:
        data = _http_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        log.debug("yahoo quote fail %s: %s", sym, exc)
        return None
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta") or {}
    ltp = float(meta.get("regularMarketPrice") or 0)
    if not ltp:
        return None
    indicators = (result.get("indicators") or {}).get("quote") or [{}]
    q0 = indicators[0] if indicators else {}
    opens = q0.get("open") or []
    highs = q0.get("high") or []
    lows = q0.get("low") or []
    vols = q0.get("volume") or []
    closes = q0.get("close") or []

    def _last(xs: list) -> float | None:
        for v in reversed(xs or []):
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    prev = None
    if len(closes) >= 2:
        # last closed bar before forming day if available
        for v in reversed(closes[:-1]):
            if v is not None:
                prev = float(v)
                break
    if prev is None:
        pc = meta.get("chartPreviousClose") or meta.get("previousClose")
        if pc is not None:
            prev = float(pc)

    return Quote(
        symbol=sym,
        ltp=ltp,
        open=_last(opens) or _f(meta.get("regularMarketOpen")),
        high=_last(highs) or _f(meta.get("regularMarketDayHigh")),
        low=_last(lows) or _f(meta.get("regularMarketDayLow")),
        prev_close=prev,
        volume=int(_last(vols) or 0) or None,
        source="yahoo_chart",
        ts_ms=int(time.time() * 1000),
    )


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def fetch_quotes_yfinance(symbols: list[str]) -> list[Quote]:
    """Batch via Yahoo chart API (name kept for call-site compat)."""
    out: list[Quote] = []
    for s in symbols:
        q = fetch_one_yahoo(s)
        if q:
            out.append(q)
        time.sleep(0.15)  # be polite to Yahoo
    return out


def quotes_to_dict(quotes: list[Quote]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": q.symbol,
            "ltp": q.ltp,
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "prev_close": q.prev_close,
            "volume": q.volume,
            "source": q.source,
            "ts_ms": q.ts_ms,
        }
        for q in quotes
    ]


def quotes_cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / "quotes_cache.json"


def write_quotes_cache(data_dir: Path, quotes: list[Quote], *, source: str = "yahoo") -> dict[str, Any]:
    payload = {
        "ts_ms": int(time.time() * 1000),
        "quotes": quotes_to_dict(quotes),
        "source": source,
    }
    path = quotes_cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def read_quotes_cache(data_dir: Path) -> dict[str, Any]:
    p = quotes_cache_path(data_dir)
    if not p.exists():
        return {"ts_ms": 0, "quotes": [], "source": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ts_ms": 0, "quotes": [], "source": None}


def refresh_default_universe(data_dir: Path, *, n: int = 20) -> dict[str, Any]:
    from data.instruments import NIFTY100_SEED

    symbols = list(NIFTY100_SEED)[: max(1, min(n, 40))]
    quotes = fetch_quotes_yfinance(symbols)
    return write_quotes_cache(data_dir, quotes, source="yahoo_chart")
