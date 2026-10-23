"""Headline dedupe + tag helpers (PLAN_V2 V1b-3)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_TITLE_NORM = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str) -> str:
    return _TITLE_NORM.sub(" ", title.lower()).strip()


def external_id_for(*, source: str, link: str | None, title: str) -> str:
    if link:
        return f"{source}:{link.strip()}"
    digest = hashlib.sha1(normalize_title(title).encode()).hexdigest()[:16]
    return f"{source}:t:{digest}"


def near_duplicate(a: str, b: str) -> bool:
    """True when normalized titles match or one contains the other (≥12 chars)."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 12 and len(nb) >= 12 and (na in nb or nb in na):
        return True
    return False


@dataclass(frozen=True)
class HeadlineIn:
    source: str
    title: str
    link: str | None
    published_ms: int | None
    ts_ms: int
    event_type: str
    symbol: str
    score: float
    confidence: float
    market: str = "IN"


def dedupe_batch(rows: list[HeadlineIn]) -> list[HeadlineIn]:
    """Drop duplicates by external_id and near-duplicate titles within the batch."""
    seen_ids: set[str] = set()
    kept: list[HeadlineIn] = []
    for r in rows:
        eid = external_id_for(source=r.source, link=r.link, title=r.title)
        if eid in seen_ids:
            continue
        if any(near_duplicate(r.title, k.title) for k in kept):
            continue
        seen_ids.add(eid)
        kept.append(r)
    return kept
