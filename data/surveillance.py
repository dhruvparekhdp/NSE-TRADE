"""ASM/GSM exclusion list (PLAN_V2 V1-5)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_surveillance_symbols(path: Path | None = None) -> frozenset[str]:
    p = path or Path(__file__).resolve().parent.parent / "config" / "surveillance.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    syms = set()
    for key in ("asm", "gsm", "symbols"):
        for s in raw.get(key) or []:
            syms.add(str(s).upper())
    return frozenset(syms)
