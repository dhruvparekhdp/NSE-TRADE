"""FII / DII provisional cash flows from the NSE website (PLAN_V2 V1b-1, MARKET_INDIA §8).

WHY: foreign selling drove most big Nifty drawdowns. NSE publishes provisional net flows around 18:00
IST; they are known only after the close, so for day T the usable value is the one for the previous
trading day (no lookahead). Unofficial endpoint (`/api/fiidiiTradeReact`, VERIFY): a failure stores
nothing and the caller shows "unavailable". RECORDING AND DISPLAY ONLY.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from data.nse_http import JsonGetter, NseUnavailable

log = logging.getLogger(__name__)

FIIDII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"


@dataclass(frozen=True)
class FlowRow:
    trade_date: str  # ISO yyyy-mm-dd of the trading session the flows belong to
    fii_net_cr: float | None
    dii_net_cr: float | None
    source: str = "nse_fiidii"
    final: bool = False


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_nse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%d-%b-%Y").date()


def parse_fii_dii(payload: Any) -> FlowRow | None:
    """Parse NSE's list of category rows into one FlowRow. Returns None on an unknown shape."""
    if not isinstance(payload, list):
        return None
    fii = dii = None
    day: date | None = None
    for row in payload:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("category", "")).upper()
        net = _num(row.get("netValue"))
        if row.get("date"):
            try:
                day = _parse_nse_date(row["date"])
            except ValueError:
                continue
        if "FII" in cat or "FPI" in cat:
            fii = net
        elif "DII" in cat:
            dii = net
    if day is None or (fii is None and dii is None):
        return None
    return FlowRow(trade_date=day.isoformat(), fii_net_cr=fii, dii_net_cr=dii)


def save_flow(conn: sqlite3.Connection, row: FlowRow) -> None:
    """Upsert, but never overwrite a final row with a provisional one."""
    conn.execute(
        "INSERT INTO flows(trade_date, fii_net_cr, dii_net_cr, source, final) VALUES (?,?,?,?,?) "
        "ON CONFLICT(trade_date) DO UPDATE SET fii_net_cr=excluded.fii_net_cr, "
        "dii_net_cr=excluded.dii_net_cr, source=excluded.source, final=excluded.final "
        "WHERE flows.final=0",
        (row.trade_date, row.fii_net_cr, row.dii_net_cr, row.source, int(row.final)),
    )
    conn.commit()


def refresh_flows(conn: sqlite3.Connection, get_json: JsonGetter) -> FlowRow | None:
    """Fetch, parse and store. None means unavailable (logged, never raised)."""
    try:
        row = parse_fii_dii(get_json(FIIDII_URL))
    except NseUnavailable as exc:
        log.warning("fii/dii unavailable: %s", exc)
        return None
    if row is not None:
        save_flow(conn, row)
    return row


def flow_for(conn: sqlite3.Connection, trade_date: str) -> FlowRow | None:
    r = conn.execute("SELECT * FROM flows WHERE trade_date=?", (trade_date,)).fetchone()
    if r is None:
        return None
    return FlowRow(
        trade_date=r["trade_date"],
        fii_net_cr=r["fii_net_cr"],
        dii_net_cr=r["dii_net_cr"],
        source=r["source"] or "",
        final=bool(r["final"]),
    )


def latest_flow_before(conn: sqlite3.Connection, trade_date: str) -> FlowRow | None:
    """Newest flow row strictly before `trade_date` (the only one known at that day's open)."""
    r = conn.execute(
        "SELECT trade_date FROM flows WHERE trade_date<? ORDER BY trade_date DESC LIMIT 1",
        (trade_date,),
    ).fetchone()
    return flow_for(conn, r["trade_date"]) if r else None


def flow_is_stale(row: FlowRow | None, trade_date: str, *, max_gap_days: int = 5) -> bool:
    """Stale if missing or older than a long weekend + a day before `trade_date`."""
    if row is None:
        return True
    return date.fromisoformat(trade_date) - date.fromisoformat(row.trade_date) > timedelta(days=max_gap_days)
