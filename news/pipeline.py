"""Score headlines: HF FinBERT (shared Space) → India rules → composite for risk/features."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import get_settings
from integrations.hf_space import classify
from news.foreign import build_snapshot
from news.india_rules import score_from_probs
from news.scrape import Headline, ingest_headlines, read_jsonl
from news.sentiment import score_headlines


def score_batch(titles: list[str]) -> list[dict[str, Any]]:
    """Prefer HF Space classify; fall back to keyword tags."""
    probs_list = classify(titles)
    out: list[dict[str, Any]] = []
    for i, title in enumerate(titles):
        if i < len(probs_list) and isinstance(probs_list[i], dict):
            out.append(score_from_probs(probs_list[i], title))
        else:
            # rules-only fallback
            tag = score_headlines([title])
            from news.india_rules import event_type, symbol_hint

            out.append(
                {
                    "score": tag,
                    "confidence": abs(tag),
                    "event_type": event_type(title),
                    "symbol": symbol_hint(title),
                }
            )
    return out


def refresh_and_score(headlines: list[Headline]) -> dict[str, Any]:
    """Ingest + score; merge shared crypto macro titles into the day's snapshot."""
    s = get_settings()
    local = Path(s.data_dir) / "news" / "india_headlines.jsonl"
    shared = Path(s.shared_headlines_path) if s.shared_headlines_path else None
    ingest_headlines(headlines, local_path=local, shared_path=shared)

    titles = [h.title for h in headlines]
    scored = score_batch(titles) if titles else []

    shared_rows = read_jsonl(shared, limit=200) if shared else []
    macro_titles = [r["title"] for r in shared_rows if r.get("market") != "india" and r.get("title")]
    # crypto lane often omits market tag — treat unknown as macro
    if shared and not macro_titles:
        macro_titles = [r["title"] for r in shared_rows if r.get("title") and r.get("market") != "india"]

    india_score = sum(x["score"] for x in scored) / len(scored) if scored else 0.0
    macro_score = score_headlines(macro_titles) if macro_titles else 0.0
    blended = 0.6 * india_score + 0.4 * macro_score if (scored or macro_titles) else 0.0

    snap, composite = build_snapshot(
        trade_date="live",
        headlines=titles + macro_titles[:20],
        results_window=False,
    )
    # prefer explicit blend when we have structured scores
    final = blended if scored else composite
    return {
        "n_india": len(headlines),
        "n_macro_shared": len(macro_titles),
        "india_score": india_score,
        "macro_score": macro_score,
        "score": final,
        "items": [{"title": t, **sc} for t, sc in zip(titles, scored, strict=False)],
        "snapshot": snap.__dict__,
    }
