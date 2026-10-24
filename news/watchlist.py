"""Extra watchlist names merged into headline symbol hints."""

from __future__ import annotations

import csv
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT = _ROOT / "config" / "watchlist_extra.csv"


def load_extra_name_hints(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    """CSV symbol + reason → lowercase tokens for title matching."""
    p = path or _DEFAULT
    if not p.exists():
        return {}
    out: dict[str, tuple[str, ...]] = {}
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            reason = (row.get("reason") or "").strip().lower()
            if not sym:
                continue
            tokens: list[str] = [sym.lower(), sym.replace("-", "").lower()]
            for part in reason.replace("(", " ").replace(")", " ").split():
                if len(part) >= 4 and part.isalpha():
                    tokens.append(part)
            if "emudhra" in reason or sym == "EMUDRA":
                tokens.extend(["emudhra", "e-mudra", "emudra", "e mudhra"])
            out[sym] = tuple(dict.fromkeys(tokens))
    return out
