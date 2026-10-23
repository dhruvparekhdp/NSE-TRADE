"""Rule-based sentiment — no LLM on the server (plan RAM + AGENTS §10 spirit).

Composite in [-1, +1]:
  foreign (US overnight / USDINR / VIX) + FII-DII flow + headline tags + results window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BEARISH = re.compile(
    r"\b(crash|plunge|fraud|raid|default|downgrade|war|sanction|sell[- ]?off|weak|miss(es|ed)?)\b",
    re.I,
)
BULLISH = re.compile(
    r"\b(surge|rally|upgrade|record|beat|win|approval|inflow|boom|strong)\b",
    re.I,
)


@dataclass(frozen=True)
class SentimentSnapshot:
    trade_date: str
    us_overnight_pct: float | None = None  # ES/SPX proxy overnight return %
    usdinr_chg_pct: float | None = None  # + = INR weaker
    india_vix: float | None = None
    india_vix_chg: float | None = None
    fii_net_cr: float | None = None  # crore
    dii_net_cr: float | None = None
    headline_score: float = 0.0
    results_window: bool = False
    extras: dict = field(default_factory=dict)


def score_headlines(titles: list[str]) -> float:
    """Average tag score in [-1, +1]."""
    if not titles:
        return 0.0
    scores = []
    for t in titles:
        s = 0.0
        if BEARISH.search(t):
            s -= 1.0
        if BULLISH.search(t):
            s += 1.0
        scores.append(max(-1.0, min(1.0, s)))
    return sum(scores) / len(scores)


def composite_score(snap: SentimentSnapshot) -> float:
    """Weighted blend → [-1, +1]. Transparent weights for lab ablation."""
    parts: list[tuple[float, float]] = []  # (weight, value)

    if snap.us_overnight_pct is not None:
        # clip ±2% overnight → ±1
        parts.append((0.30, max(-1.0, min(1.0, snap.us_overnight_pct / 2.0))))
    if snap.usdinr_chg_pct is not None:
        # INR weaker (up) is mild risk-off for India
        parts.append((0.10, max(-1.0, min(1.0, -snap.usdinr_chg_pct / 1.0))))
    if snap.india_vix_chg is not None:
        parts.append((0.15, max(-1.0, min(1.0, -snap.india_vix_chg / 5.0))))
    elif snap.india_vix is not None:
        # level vs ~15 calm
        parts.append((0.10, max(-1.0, min(1.0, (15.0 - snap.india_vix) / 15.0))))
    if snap.fii_net_cr is not None:
        parts.append((0.25, max(-1.0, min(1.0, snap.fii_net_cr / 2000.0))))
    if snap.dii_net_cr is not None:
        parts.append((0.10, max(-1.0, min(1.0, snap.dii_net_cr / 2000.0))))
    parts.append((0.20, max(-1.0, min(1.0, snap.headline_score))))

    if not parts:
        base = 0.0
    else:
        wsum = sum(w for w, _ in parts)
        base = sum(w * v for w, v in parts) / wsum

    if snap.results_window:
        # damp conviction into results; slight negative for gap risk
        base *= 0.5
        base -= 0.1
    return max(-1.0, min(1.0, base))
