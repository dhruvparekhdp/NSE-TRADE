"""FY 2026-27 Angel ONE_MINUTE backfill for watchlist (+ optional symbols)."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config.secrets_loader import apply_db_secrets
from config.settings import get_settings
from data.history import backfill_minutes, window_30d
from data.lake import Lake
from news.watchlist import load_extra_name_hints

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
FY_START = date(2026, 4, 1)
SLEEP_S = 0.45


class _AngelCandles:
    def __init__(self, api: Any) -> None:
        self._api = api

    def get_candles(
        self, token: str, interval: str, from_dt: datetime, to_dt: datetime
    ) -> list[list[Any]]:
        payload = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        }
        data = self._api.getCandleData(payload)
        if not data or not data.get("status"):
            return []
        return list(data.get("data") or [])


def _login_api() -> Any:
    from broker.smartconnect_factory import build_smart_connect, totp_now_utc

    apply_db_secrets()
    s = get_settings()
    if not s.angel_configured:
        raise RuntimeError("Angel keys missing — fill /keys on server or .env")
    api = build_smart_connect()
    totp = totp_now_utc(s.angel_totp_secret.get_secret_value())  # type: ignore[union-attr]
    sess = api.generateSession(
        s.angel_client_code.get_secret_value(),  # type: ignore[union-attr]
        s.angel_pin.get_secret_value(),  # type: ignore[union-attr]
        totp,
    )
    if not sess.get("status"):
        raise RuntimeError(f"Angel login failed: {sess.get('message')}")
    return api


def _token_for(api: Any, symbol: str) -> str:
    r = api.searchScrip("NSE", symbol)
    if not r or not r.get("status"):
        raise RuntimeError(f"searchScrip failed for {symbol}")
    for row in r.get("data") or []:
        tsym = str(row.get("tradingsymbol") or row.get("symbol") or "")
        if tsym == f"{symbol}-EQ" or row.get("symboltoken"):
            return str(row["symboltoken"])
    raise RuntimeError(f"no NSE-EQ token for {symbol}")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--lake", type=Path, default=None)
    p.add_argument("--symbols", default=None, help="comma list; default watchlist_extra.csv")
    p.add_argument("--from", dest="from_date", default=FY_START.isoformat())
    p.add_argument("--to", dest="to_date", default=date.today().isoformat())
    args = p.parse_args()
    s = get_settings()
    lake = Lake(args.lake or Path(s.data_dir) / "lake")
    if args.symbols:
        symbols = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    else:
        symbols = sorted(load_extra_name_hints().keys())
    if not symbols:
        symbols = ["EMUDHRA"]
    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)
    api = _login_api()
    client = _AngelCandles(api)
    report: dict[str, Any] = {"symbols": {}, "fy": [start.isoformat(), end.isoformat()]}
    for sym in symbols:
        try:
            tok = _token_for(api, sym)
            windows = window_30d(start, end)
            state = Path(s.data_dir) / "state" / f"fy_1m_{sym}.json"
            n = backfill_minutes(lake, client, symbol=sym, token=tok, windows=windows, state_path=state)
            report["symbols"][sym] = {"token": tok, "bars_written": n}
            log.info("fy backfill %s bars=%s", sym, n)
        except Exception as exc:  # noqa: BLE001
            report["symbols"][sym] = {"error": str(exc)}
            log.warning("fy backfill %s failed: %s", sym, exc)
        time.sleep(SLEEP_S)
    out = Path(s.data_dir) / "reports" / "fy_angel_backfill.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "ok": sum(1 for v in report["symbols"].values() if "bars_written" in v)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
