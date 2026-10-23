"""Angel LTP with Yahoo fallback (PLAN_V2 V4-2). Display marks only — never for fills."""

from __future__ import annotations

import logging
from typing import Any, Callable

from data.free_quotes import refresh_default_universe

log = logging.getLogger(__name__)

AngelLtp = Callable[[list[str]], dict[str, float]]


def fetch_marks(
    symbols: list[str],
    *,
    data_dir,
    angel_ltp: AngelLtp | None = None,
) -> dict[str, Any]:
    """Prefer Angel batch LTP; on failure use Yahoo chart cache (VERIFY delay)."""
    marks: dict[str, float] = {}
    source = "none"
    if angel_ltp is not None:
        try:
            marks = {s: float(v) for s, v in angel_ltp(symbols).items()}
            source = "angel"
        except Exception as exc:  # noqa: BLE001
            log.warning("angel ltp failed: %s", exc)
    if not marks:
        payload = refresh_default_universe(data_dir, n=len(symbols) or 20)
        for q in payload.get("quotes") or []:
            if q.get("symbol") in symbols or not symbols:
                marks[str(q["symbol"])] = float(q["ltp"])
        source = str(payload.get("source") or "yahoo")
    return {"source": source, "marks": marks}
