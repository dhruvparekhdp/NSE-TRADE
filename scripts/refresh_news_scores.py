"""Ingest RSS headlines, dedupe, Hermes-style extract → events JSONL (no trading side effects)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from config.settings import get_settings
from news.dedupe import dedupe_titles, title_fingerprint
from news.hermes_extract import extract_event
from news.scrape import DEFAULT_FEEDS, Headline, fetch_feed
from news.watchlist import load_extra_name_hints


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            fp = row.get("fingerprint") or title_fingerprint(row.get("title", ""))
            seen.add(fp)
        except json.JSONDecodeError:
            continue
    return seen


def process_headlines(
    headlines: list[Headline],
    *,
    out_path: Path,
    use_llm: bool = False,
) -> dict[str, int]:
    """Score headlines and append new event rows."""
    extra = load_extra_name_hints()
    seen = _load_seen(out_path)
    titles = [h.title for h in headlines]
    new_titles, seen = dedupe_titles(titles, seen)
    title_to_h = {h.title: h for h in headlines}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = {"ingested": 0, "skipped_dup": len(titles) - len(new_titles)}
    with out_path.open("a", encoding="utf-8") as f:
        for title in new_titles:
            h = title_to_h[title]
            ev = extract_event(title, use_llm=use_llm, extra_names=extra)
            row: dict[str, Any] = {
                "published_ms": h.published_ms,
                "source": h.source,
                "title": h.title,
                "link": h.link,
                "external_id": h.external_id,
                "fingerprint": title_fingerprint(title),
                "extracted_ms": int(time.time() * 1000),
                **ev,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            stats["ingested"] += 1
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh news event scores")
    p.add_argument("--out", type=Path, default=None, help="events jsonl (default data/news/events.jsonl)")
    p.add_argument("--llm", action="store_true", help="use Groq/OpenRouter extract when configured")
    p.add_argument("--no-fetch", action="store_true", help="skip RSS fetch (use with tests / empty run)")
    args = p.parse_args()
    s = get_settings()
    out = args.out or Path(s.data_dir) / "news" / "events.jsonl"
    headlines: list[Headline] = []
    if not args.no_fetch:
        for source, url in DEFAULT_FEEDS:
            try:
                headlines.extend(fetch_feed(url, source))
            except OSError as exc:
                print(json.dumps({"warn": source, "error": str(exc)}))
    stats = process_headlines(headlines, out_path=out, use_llm=args.llm)
    print(json.dumps({"out": str(out), **stats}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
