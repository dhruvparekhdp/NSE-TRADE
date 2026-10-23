"""India RSS scrape + shared headlines lane with crypto (no network in unit tests)."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

# Free RSS endpoints (may change; fixtures cover tests)
DEFAULT_FEEDS = [
    ("moneycontrol", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("economictimes", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
]


@dataclass(frozen=True)
class Headline:
    source: str
    title: str
    link: str
    published_ms: int
    external_id: str


def parse_rss(xml_text: str, source: str) -> list[Headline]:
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    out: list[Headline] = []
    for it in items:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title:
            continue
        guid = (it.findtext("guid") or link or title).strip()
        out.append(
            Headline(
                source=source,
                title=title,
                link=link,
                published_ms=int(time.time() * 1000),
                external_id=f"{source}:{guid}"[:240],
            )
        )
    return out


def fetch_feed(url: str, source: str, timeout: float = 15.0) -> list[Headline]:
    req = Request(url, headers={"User-Agent": "nse-engine/0.1 (research; contact owner)"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — explicit allowlist URLs
        raw = resp.read().decode("utf-8", errors="replace")
    return parse_rss(raw, source)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def ingest_headlines(
    headlines: list[Headline],
    *,
    local_path: Path,
    shared_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Write India headlines locally and optionally append to shared lane for crypto to see."""
    rows = [
        {
            "ts_ms": h.published_ms,
            "source": h.source,
            "title": h.title,
            "link": h.link,
            "external_id": h.external_id,
            "market": "india",
        }
        for h in headlines
    ]
    if rows:
        append_jsonl(local_path, rows)
        if shared_path is not None:
            append_jsonl(shared_path, rows)
    return rows
