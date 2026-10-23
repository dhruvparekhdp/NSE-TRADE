"""Resumable NSE bhavcopy downloader (PLAN_V2 V3-1). Owner runs this; max 1 req / 2s.

  python -m scripts.download_bhav --from 2012-01-01 --to 2026-10-23
"""

from __future__ import annotations

import argparse
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from data.calendar import CalendarMissing, load_default_calendar

# NSE path patterns change; VERIFY. Throttle is mandatory.
LEGACY_URL = "https://archives.nseindia.com/content/historical/EQUITIES/{yyyy}/{mon}/cm{dd}{mon}{yyyy}bhav.csv.zip"
UDIFF_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
_UA = "Mozilla/5.0 (compatible; nse-engine-research/0.1)"


def _dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def download_day(d: date, dest: Path, *, sleep_s: float = 2.0) -> str:
    """Return 'ok' | 'skip' | 'fail'. Never raises for HTTP errors."""
    dest.mkdir(parents=True, exist_ok=True)
    yyyymmdd = d.strftime("%Y%m%d")
    out = dest / f"bhav_{yyyymmdd}.csv"
    if out.exists() and out.stat().st_size > 0:
        return "skip"
    mon = d.strftime("%b").upper()
    urls = [
        UDIFF_URL.format(yyyymmdd=yyyymmdd),
        LEGACY_URL.format(yyyy=d.year, mon=mon, dd=f"{d.day:02d}"),
    ]
    for url in urls:
        try:
            req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
            with urlopen(req, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
            tmp = out.with_suffix(".zip")
            tmp.write_bytes(raw)
            try:
                with zipfile.ZipFile(tmp) as zf:
                    name = zf.namelist()[0]
                    out.write_bytes(zf.read(name))
            except zipfile.BadZipFile:
                out.write_bytes(raw)
            finally:
                tmp.unlink(missing_ok=True)
            time.sleep(sleep_s)
            return "ok"
        except (HTTPError, URLError, TimeoutError, OSError):
            continue
    time.sleep(sleep_s)
    return "fail"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--out", default="var/bhav")
    p.add_argument("--sleep", type=float, default=2.0)
    args = p.parse_args(argv)
    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    cal = None
    try:
        cal = load_default_calendar()
    except CalendarMissing:
        pass
    stats = {"ok": 0, "skip": 0, "fail": 0, "holiday": 0}
    for d in _dates(start, end):
        if cal is not None:
            try:
                if not cal.is_trading_day(d):
                    stats["holiday"] += 1
                    continue
            except CalendarMissing:
                pass
        elif d.weekday() >= 5:
            stats["holiday"] += 1
            continue
        stats[download_day(d, Path(args.out), sleep_s=args.sleep)] += 1
        print(f"{d.isoformat()} {stats}")
    print({"done": True, **stats, "finished_at": datetime.utcnow().isoformat() + "Z"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
