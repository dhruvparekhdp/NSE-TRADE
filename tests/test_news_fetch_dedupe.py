"""job_news fetched nothing (empty list stub) and re-stored the same feed items every run; 26 Oct 2026."""

from __future__ import annotations

from news.scrape import Headline, fetch_all, ingest_headlines, read_jsonl


def _h(i: int, src: str = "mc") -> Headline:
    return Headline(source=src, title=f"t{i}", link=f"https://x/{i}", published_ms=i, external_id=f"id{i}")


def test_fetch_all_skips_a_failing_feed():
    def fake(url, source):
        if source == "bad":
            raise TimeoutError("down")
        return [_h(1, source)]

    warnings = []

    class Log:
        def warning(self, *a):
            warnings.append(a)

    out = fetch_all([("good", "u1"), ("bad", "u2"), ("good2", "u3")], fetch=fake, log=Log())
    assert [h.source for h in out] == ["good", "good2"] and len(warnings) == 1


def test_ingest_stores_each_headline_once(tmp_path):
    path = tmp_path / "india.jsonl"
    assert len(ingest_headlines([_h(1), _h(2)], local_path=path)) == 2
    ingest_headlines([_h(1), _h(2), _h(3)], local_path=path)   # next 15-minute run: one new item
    assert [r["external_id"] for r in read_jsonl(path)] == ["id1", "id2", "id3"]
