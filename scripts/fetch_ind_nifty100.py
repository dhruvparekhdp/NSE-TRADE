"""Download NSE ind_nifty100list.csv (Industry column) for sector cap (N4)."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://archives.nseindia.com/content/indices/ind_nifty100list.csv"
_UA = "Mozilla/5.0 (compatible; nse-engine-research/0.1)"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="config/ind_nifty100list.csv")
    args = p.parse_args(argv)
    req = Request(URL, headers={"User-Agent": _UA, "Accept": "text/csv,*/*"})
    with urlopen(req, timeout=30) as resp:  # noqa: S310
        data = resp.read()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print({"written": str(out), "bytes": len(data)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
