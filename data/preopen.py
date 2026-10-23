"""NSE pre-open auction snapshots (PLAN_V2 V1b-2). Recording only."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from data.nse_http import JsonGetter, NseUnavailable

log = logging.getLogger(__name__)

PREOPEN_NIFTY_URL = "https://www.nseindia.com/api/market-data-pre-open?key=NIFTY"
PREOPEN_FO_URL = "https://www.nseindia.com/api/market-data-pre-open?key=FO"


@dataclass(frozen=True)
class PreopenSnap:
    trade_date: str
    ts_ms: int
    symbol: str
    iep: float | None
    prev_close: float | None
    chg_pct: float | None
    buy_qty: int
    sell_qty: int
    final: bool
    source: str = "nse_preopen"

    @property
    def imbalance(self) -> float | None:
        tot = self.buy_qty + self.sell_qty
        if tot <= 0:
            return None
        return (self.buy_qty - self.sell_qty) / tot


def parse_preopen_payload(
    raw: dict[str, Any],
    *,
    trade_date: str,
    ts_ms: int,
    final: bool = False,
    source: str = "nse_preopen",
) -> list[PreopenSnap]:
    """Parse NSE pre-open style JSON (`key=NIFTY` / FO list) into snapshot rows."""
    rows_in = raw.get("data") or raw.get("rows") or []
    out: list[PreopenSnap] = []
    for r in rows_in:
        sym = str(r.get("symbol") or r.get("symbolName") or "").upper()
        if not sym:
            continue
        iep = r.get("iep") if r.get("iep") is not None else r.get("lastPrice")
        prev = r.get("prev_close") if r.get("prev_close") is not None else r.get("previousClose")
        chg = None
        if iep is not None and prev not in (None, 0):
            chg = (float(iep) - float(prev)) / float(prev) * 100.0
        out.append(
            PreopenSnap(
                trade_date=trade_date,
                ts_ms=ts_ms,
                symbol=sym,
                iep=float(iep) if iep is not None else None,
                prev_close=float(prev) if prev is not None else None,
                chg_pct=chg,
                buy_qty=int(r.get("buy_qty") or r.get("totalBuyQuantity") or 0),
                sell_qty=int(r.get("sell_qty") or r.get("totalSellQuantity") or 0),
                final=final,
                source=source,
            )
        )
    return out


def mark_final(snaps: list[PreopenSnap]) -> list[PreopenSnap]:
    """Copy snaps with final=1 (last pre-open batch before 09:15)."""
    return [
        PreopenSnap(
            trade_date=s.trade_date,
            ts_ms=s.ts_ms,
            symbol=s.symbol,
            iep=s.iep,
            prev_close=s.prev_close,
            chg_pct=s.chg_pct,
            buy_qty=s.buy_qty,
            sell_qty=s.sell_qty,
            final=True,
            source=s.source,
        )
        for s in snaps
    ]


def save_preopen_snaps(conn: sqlite3.Connection, snaps: list[PreopenSnap]) -> int:
    n = 0
    for s in snaps:
        conn.execute(
            "INSERT OR REPLACE INTO preopen_snapshots"
            "(trade_date, ts_ms, symbol, iep, prev_close, chg_pct, buy_qty, sell_qty, final, source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                s.trade_date,
                s.ts_ms,
                s.symbol,
                s.iep,
                s.prev_close,
                s.chg_pct,
                s.buy_qty,
                s.sell_qty,
                int(s.final),
                s.source,
            ),
        )
        n += 1
    conn.commit()
    return n


def refresh_preopen(
    conn: sqlite3.Connection,
    get_json: JsonGetter,
    *,
    trade_date: str,
    ts_ms: int,
    final: bool = False,
) -> list[PreopenSnap]:
    """Fetch NIFTY + FO pre-open JSON; store rows. Empty on NSE block (logged)."""
    snaps: list[PreopenSnap] = []
    for url in (PREOPEN_NIFTY_URL, PREOPEN_FO_URL):
        try:
            raw = get_json(url)
        except NseUnavailable as exc:
            log.warning("preopen unavailable (%s): %s", url, exc)
            continue
        if not isinstance(raw, dict):
            continue
        snaps.extend(
            parse_preopen_payload(raw, trade_date=trade_date, ts_ms=ts_ms, final=final)
        )
    if final:
        snaps = mark_final(snaps)
    if snaps:
        save_preopen_snaps(conn, snaps)
    return snaps
