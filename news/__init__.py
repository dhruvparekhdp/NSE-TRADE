"""News + foreign sentiment features/filters (owner decision 2026-10-23). Off by default."""

from news.sentiment import SentimentSnapshot, composite_score, score_headlines

__all__ = ["SentimentSnapshot", "composite_score", "score_headlines"]
