"""NSE-005: docs/reconciliation.md names every remote branch and a recommendation.

The branch list is the origin/* snapshot taken 6 Nov 2026 (IST), excluding main.
A later branch is a new snapshot, not a silent edit of this list.
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "reconciliation.md"

# origin/* at aae5f1f after git fetch on 6 Nov 2026. main is the base, not a row.
BRANCHES = (
    "deploy/20261026",
    "feat/c17-paper-book",
    "feat/c19-monday-paper",
    "feat/mvp-backtest-news",
    "feat/portal-hubs",
    "feat/review-v-fix-2",
    "feat/review-v0-v6",
    "feat/v-fix-1",
    "feat/v-fix-2",
    "feat/v-fix-2-login",
    "feat/v-next",
    "feat/v0-hygiene",
    "feat/v1-market",
    "feat/v1b-opening",
    "feat/v2-lab-fixes",
    "feat/v3-research",
    "feat/v4-paper",
    "feat/v5-portal",
    "feat/v6-intraday-shadow",
    "feat/v8-complete",
    "feat/v8-news-p0",
    "feat/v9-plan",
    "fix/c19-review",
    "fix/monotonic-cooldown",
    "fix/runtime-overrides",
    "jarvis/AUD-3",
    "jarvis/NSE-004",
    "jarvis/NSE-006",
    "jarvis/nse-001",
    "jarvis/nse-003",
)

RECOMMENDATIONS = ("merge", "cherry-pick", "drop")


def test_reconciliation_doc_exists():
    assert DOC.is_file(), "docs/reconciliation.md is the NSE-005 deliverable"


def test_every_branch_has_a_recommendation():
    text = DOC.read_text(encoding="utf-8")
    missing: list[str] = []
    for branch in BRANCHES:
        line = next((row for row in text.splitlines() if branch in row), "")
        if not any(word in line for word in RECOMMENDATIONS):
            missing.append(branch)
    assert not missing, f"branches without a recommendation on their line: {missing}"


def test_report_covers_stores_and_deploy():
    text = DOC.read_text(encoding="utf-8")
    for needle in ("SQLite", "Postgres", "single source of truth", "Deployment"):
        assert needle in text
