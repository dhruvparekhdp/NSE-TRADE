"""Shared crypto infra: RSS parse, India rules, budget, pipeline offline."""

from __future__ import annotations

from integrations.llm_budget import reset_budget_for_tests
from news.india_rules import event_type, score_from_probs, symbol_hint
from news.pipeline import score_batch
from news.scrape import ingest_headlines, parse_rss, read_jsonl

RSS = """<?xml version="1.0"?>
<rss><channel>
<item><title>RBI holds repo rate</title><link>http://x/1</link><guid>g1</guid></item>
<item><title>FII inflows surge into equities</title><link>http://x/2</link><guid>g2</guid></item>
</channel></rss>
"""


def test_parse_rss_and_shared_lane(tmp_path):
    heads = parse_rss(RSS, "moneycontrol")
    assert len(heads) == 2
    local = tmp_path / "india.jsonl"
    shared = tmp_path / "shared.jsonl"
    ingest_headlines(heads, local_path=local, shared_path=shared)
    rows = read_jsonl(shared)
    assert rows[0]["market"] == "india"
    assert "RBI" in rows[0]["title"]


def test_india_rules():
    assert event_type("RBI MPC keeps repo rate unchanged") == "rbi_policy"
    assert symbol_hint("Infosys Q2 net profit rises") == "INFY"
    scored = score_from_probs({"positive": 0.2, "negative": 0.7}, "ED raid on banking fraud")
    assert scored["score"] < 0


def test_score_batch_rules_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from config.settings import reset_settings_cache

    reset_settings_cache()
    reset_budget_for_tests(tmp_path / "budget.json")

    def _no_hf(_texts):
        return []

    monkeypatch.setattr("news.pipeline.classify", _no_hf)
    out = score_batch(["Market crash after fraud raid", "Record rally upgrade"])
    assert len(out) == 2
    assert out[0]["score"] <= 0


def test_budget_blocks_after_limit(tmp_path):
    b = reset_budget_for_tests(tmp_path / "b.json")
    b.limits["groq/*"] = {"rpm": 1, "rpd": 1, "tpm": None, "tpd": None}
    assert b.allow("groq", "m")[0] is True
    b.observe("groq", "m", 10)
    ok, _, why = b.allow("groq", "m")
    assert ok is False
    assert why in {"rpd", "rpm"}
