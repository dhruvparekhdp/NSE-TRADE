"""NSE pre-open rows are nested (metadata + detail.preOpenMarket); the 26 Oct 2026 job saved 0 rows from 213."""

from __future__ import annotations

import json
from pathlib import Path

from data.preopen import PREOPEN_NIFTY_URL, parse_preopen_payload

FIX = Path(__file__).parent / "fixtures" / "nse_preopen_fo_20261026.json"


def test_parses_real_nested_nse_rows():
    raw = json.loads(FIX.read_text())
    snaps = parse_preopen_payload(raw, trade_date="2026-10-26", ts_ms=1, final=False)
    assert len(snaps) == len(raw["data"]) == 2
    first, meta = snaps[0], raw["data"][0]["metadata"]
    pom = raw["data"][0]["detail"]["preOpenMarket"]
    assert first.symbol == meta["symbol"]
    assert first.iep == float(meta["iep"]) and first.prev_close == float(meta["previousClose"])
    assert first.buy_qty == int(pom["totalBuyQuantity"]) and first.sell_qty == int(pom["totalSellQuantity"])
    assert abs(first.chg_pct - (meta["iep"] / meta["previousClose"] - 1) * 100) < 1e-9


def test_flat_rows_still_parse():
    raw = {"data": [{"symbol": "X", "iep": 101, "previousClose": 100}]}
    snaps = parse_preopen_payload(raw, trade_date="d", ts_ms=1)
    assert snaps[0].symbol == "X" and abs(snaps[0].chg_pct - 1.0) < 1e-9


def test_nifty_url_uses_nifty_50_key():
    assert PREOPEN_NIFTY_URL.endswith("key=NIFTY%2050")
