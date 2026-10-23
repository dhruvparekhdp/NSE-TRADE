"""Global cues: US / Europe / Asia indices, futures, FX, crude, gold, bonds, Nifty, VIX (PLAN_V2 V1b-1).

WHY (D8, MARKET_INDIA §8b): the Indian open is where overnight news lands, so we record every cue
every `cues_poll_s` seconds. RECORDING AND DISPLAY ONLY: nothing here may block, size or time a trade.

Each row keeps its own previous close, so the change is "vs that market's last close", never a
made-up 0%. A row is `stale` when its market is closed (last trade older than 2x the poll interval)
or Yahoo returned no trade time. A closed market therefore shows its last real move, flagged stale.
Yahoo's chart API is unofficial (VERIFY symbols and per-symbol delays); failures store nothing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import get_settings

log = logging.getLogger(__name__)

CUES_PATH = Path(__file__).resolve().parent.parent / "config" / "cues.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
_UA = "Mozilla/5.0 (compatible; nse-engine/0.1; research)"
_DAY_MS = 86_400_000

YahooFetch = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class CueSpec:
    key: str
    label: str
    region: str
    symbol: str | None
    source: str
    delay_s: int = 0


@dataclass(frozen=True)
class CueRow:
    ts_ms: int
    key: str
    last: float | None
    chg_pct: float | None
    ref_close: float | None
    source: str
    stale: bool
    mkt_ts_ms: int | None = None


def load_cue_specs(path: Path | None = None) -> list[CueSpec]:
    raw = json.loads((path or CUES_PATH).read_text(encoding="utf-8"))
    return [
        CueSpec(
            key=r["key"],
            label=r["label"],
            region=r["region"],
            symbol=r.get("symbol"),
            source=r.get("source", "yahoo"),
            delay_s=int(r.get("delay_s") or 0),
        )
        for r in raw["instruments"]
    ]


def fetch_yahoo_chart(symbol: str, *, timeout: float = 12.0) -> dict[str, Any]:
    """Network call (scripts / jobs only; tests inject a fake)."""
    url = YAHOO_CHART.format(symbol=urllib.parse.quote(symbol, safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed Yahoo host
        return json.loads(resp.read().decode("utf-8"))


def _prev_close(result: dict[str, Any], mkt_ts_s: int | None) -> float | None:
    """Close of the last session *before* the one that produced the last price.

    Yahoo's `chartPreviousClose` is the close before the whole 5-day range, so it is not used.
    """
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    offset = int(meta.get("gmtoffset") or 0)
    if mkt_ts_s is not None:
        today = (mkt_ts_s + offset) // 86_400
        earlier = [
            float(c) for t, c in zip(stamps, closes, strict=False)
            if c is not None and (int(t) + offset) // 86_400 < today
        ]
        if earlier:
            return earlier[-1]
    pc = meta.get("previousClose")
    return float(pc) if pc else None


def parse_yahoo_chart(
    payload: dict[str, Any],
    spec: CueSpec,
    *,
    now_ms: int,
    interval_s: int,
) -> CueRow | None:
    """Turn one Yahoo chart payload into a cue row, or None if Yahoo had no price."""
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta") or {}
    last = meta.get("regularMarketPrice")
    if last is None:
        return None
    last = float(last)
    mkt_s = meta.get("regularMarketTime")
    mkt_ms = int(mkt_s) * 1000 if mkt_s else None
    ref = _prev_close(result, int(mkt_s) if mkt_s else None)
    chg = round((last - ref) / ref * 100.0, 4) if ref else None  # unknown stays None, never 0
    limit_ms = (2 * interval_s + spec.delay_s) * 1000
    stale = mkt_ms is None or (now_ms - mkt_ms) > limit_ms
    return CueRow(
        ts_ms=now_ms,
        key=spec.key,
        last=last,
        chg_pct=chg,
        ref_close=ref,
        source="yahoo",
        stale=stale,
        mkt_ts_ms=mkt_ms,
    )


def save_cue_rows(conn: sqlite3.Connection, rows: Iterable[CueRow]) -> int:
    n = 0
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO global_cues"
            "(ts_ms, key, last, chg_pct, ref_close, source, stale, mkt_ts_ms) VALUES (?,?,?,?,?,?,?,?)",
            (r.ts_ms, r.key, r.last, r.chg_pct, r.ref_close, r.source, int(r.stale), r.mkt_ts_ms),
        )
        n += 1
    conn.commit()
    return n


def refresh_cues(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    fetch: YahooFetch = fetch_yahoo_chart,
    specs: list[CueSpec] | None = None,
    interval_s: int | None = None,
) -> list[CueRow]:
    """Poll every Yahoo-sourced cue once. One failing symbol never stops the others."""
    interval = interval_s if interval_s is not None else get_settings().cues_poll_s
    rows: list[CueRow] = []
    for spec in specs or load_cue_specs():
        if spec.source != "yahoo" or not spec.symbol:
            continue
        try:
            row = parse_yahoo_chart(fetch(spec.symbol), spec, now_ms=now_ms, interval_s=interval)
        except Exception as exc:  # noqa: BLE001 — unofficial source; log and move on
            log.warning("cue %s fetch failed: %s", spec.key, exc)
            continue
        if row is not None:
            rows.append(row)
    save_cue_rows(conn, rows)
    return rows


def latest_cues(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    interval_s: int | None = None,
) -> dict[str, CueRow]:
    """Newest row per key at or before `now_ms` (no lookahead).

    A row is also marked stale here if our own poll is older than 2x the interval (the poller died).
    """
    interval = interval_s if interval_s is not None else get_settings().cues_poll_s
    out: dict[str, CueRow] = {}
    q = (
        "SELECT g.* FROM global_cues g JOIN "
        "(SELECT key, MAX(ts_ms) AS m FROM global_cues WHERE ts_ms<=? GROUP BY key) x "
        "ON g.key=x.key AND g.ts_ms=x.m"
    )
    for r in conn.execute(q, (now_ms,)):
        poll_old = now_ms - int(r["ts_ms"]) > 2 * interval * 1000
        out[r["key"]] = CueRow(
            ts_ms=int(r["ts_ms"]),
            key=r["key"],
            last=r["last"],
            chg_pct=r["chg_pct"],
            ref_close=r["ref_close"],
            source=r["source"],
            stale=bool(r["stale"]) or poll_old,
            mkt_ts_ms=r["mkt_ts_ms"],
        )
    return out


def usable_overnight(row: CueRow | None, *, now_ms: int, max_age_days: int = 4) -> bool:
    """A stale cue (market closed) still describes the last session, unless it is days old."""
    if row is None or row.chg_pct is None:
        return False
    if row.mkt_ts_ms is None:
        return False
    return now_ms - row.mkt_ts_ms <= max_age_days * _DAY_MS


def window_change_pct(
    conn: sqlite3.Connection,
    key: str,
    *,
    now_ms: int,
    window_ms: int,
) -> float | None:
    """% change of `key` between its oldest and newest *live* snapshot inside the window.

    Stale snapshots are ignored: a closed market cannot be "moving". Needs two live points.
    """
    rows = conn.execute(
        "SELECT ts_ms, last FROM global_cues WHERE key=? AND stale=0 AND last IS NOT NULL "
        "AND ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
        (key, now_ms - window_ms, now_ms),
    ).fetchall()
    if len(rows) < 2 or not rows[0]["last"]:
        return None
    first, last = float(rows[0]["last"]), float(rows[-1]["last"])
    return (last - first) / first * 100.0


def overnight_proxy_pct(cues: dict[str, CueRow], *, now_ms: int) -> float | None:
    """Stand-in for GIFT Nifty while `gift_nifty_source=none` (Q11): mean of US futures and Asia.

    Shown as a proxy, never stored under the GIFTNIFTY key.
    """
    vals = [
        cues[k].chg_pct
        for k in ("ES", "NQ", "N225", "HSI", "KOSPI")
        if k in cues and usable_overnight(cues[k], now_ms=now_ms)
    ]
    return round(sum(vals) / len(vals), 4) if vals else None  # type: ignore[arg-type]
