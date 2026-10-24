"""V8-P0: Hermes-style headline dedupe and event extract (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from news.dedupe import dedupe_titles, title_fingerprint
from news.hermes_extract import extract_from_rules, merge_llm
from news.scrape import Headline
from news.watchlist import load_extra_name_hints
from scripts.refresh_news_scores import process_headlines


def test_dedupe_titles():
    seen: set[str] = set()
    a, seen = dedupe_titles(["Foo Bar", "foo  bar", "Other"], seen)
    assert a == ["Foo Bar", "Other"]
    b, _ = dedupe_titles(["Other"], seen)
    assert b == []


def test_fingerprint_stable():
    assert title_fingerprint("A") == title_fingerprint("  a  ")


def test_cyber_breach_emudhra_rules():
    extra = load_extra_name_hints()
    title = "eMudhra faces security lapse; shares fall 8% on NSE"
    ev = extract_from_rules(title, extra_names=extra)
    assert ev["event_type"] == "cyber_breach"
    assert ev["severity"] <= -0.3
    assert "EMUDHRA" in ev["symbols"]
    assert ev["is_company_specific"] is True


def test_process_headlines_jsonl(tmp_path: Path):
    out = tmp_path / "events.jsonl"
    hs = [
        Headline(
            source="test",
            title="RBI keeps repo rate unchanged",
            link="",
            published_ms=1,
            external_id="t1",
        ),
        Headline(
            source="test",
            title="RBI keeps repo rate unchanged",
            link="",
            published_ms=2,
            external_id="t2",
        ),
    ]
    s1 = process_headlines(hs, out_path=out, use_llm=False)
    assert s1["ingested"] == 1
    assert s1["skipped_dup"] == 1
    s2 = process_headlines(hs, out_path=out, use_llm=False)
    assert s2["ingested"] == 0
    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert rows[0]["event_type"] == "rbi_policy"


def test_merge_llm_overrides_symbols():
    rules = extract_from_rules("Generic market selloff")
    llm = {
        "symbols": ["SBIN"],
        "event_type": "banking_stress",
        "severity": -0.7,
        "summary": "SBI stress",
        "is_company_specific": True,
    }
    m = merge_llm(rules, llm)
    assert m["symbols"] == ["SBIN"]
    assert m["severity"] == -0.7
