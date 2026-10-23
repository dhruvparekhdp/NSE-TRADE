"""Block deploys during NSE market hours unless force=true (plan A14.1)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def deploy_blocked(now: datetime | None = None, *, force: bool = False) -> bool:
    """Return True if deploy should be refused.

    Mon–Fri 09:00–15:45 IST inclusive window (plan A14.1).
    """
    if force:
        return False
    dt = now.astimezone(IST) if now else datetime.now(tz=IST)
    if dt.weekday() >= 5:
        return False
    hhmm = dt.hour * 100 + dt.minute
    return 900 <= hhmm <= 1545


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exit 1 if deploy is blocked by market hours")
    parser.add_argument("--force", default="false")
    args = parser.parse_args(argv)
    force = str(args.force).lower() in {"1", "true", "yes"}
    if deploy_blocked(force=force):
        print(
            "Market hours (IST) - deploy blocked. Re-run after 15:45 or dispatch with force=true.",
            file=sys.stderr,
        )
        return 1
    print("deploy allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
