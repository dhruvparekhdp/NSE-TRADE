"""Headline dedupe by normalized title hash (Hermes-style; embed optional later)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation edges for stable keys."""
    t = _WS.sub(" ", title.strip().lower())
    return t[:500]


def title_fingerprint(title: str) -> str:
    """Stable id for dedupe within a rolling window."""
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()[:32]


def dedupe_titles(titles: Iterable[str], seen: set[str] | None = None) -> tuple[list[str], set[str]]:
    """Return new titles not in seen; updates seen with fingerprints."""
    bag = seen if seen is not None else set()
    out: list[str] = []
    for t in titles:
        fp = title_fingerprint(t)
        if fp in bag:
            continue
        bag.add(fp)
        out.append(t)
    return out, bag
