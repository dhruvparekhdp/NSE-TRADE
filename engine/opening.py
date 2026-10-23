"""Morning brief, opening type, risk-off alarm (PLAN_V2 V1b-4). Display/research only — never sizes trades."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

OPENING_TYPES = (
    "gap-up-and-go",
    "gap-up-fade",
    "gap-down-recover",
    "gap-down-go",
    "flat",
)


def classify_opening(*, gap_pct: float, open_px: float, close_px: float, threshold: float = 0.5) -> str:
    """Opening type at 15:45 (PLAN_V2 V1b-4 / MARKET_INDIA §8b)."""
    if gap_pct >= threshold:
        return "gap-up-and-go" if close_px > open_px else "gap-up-fade"
    if gap_pct <= -threshold:
        return "gap-down-recover" if close_px > open_px else "gap-down-go"
    return "flat"


def open_type_so_far(
    *,
    gap_pct: float,
    open_px: float,
    last_px: float,
    finalized: bool,
    threshold: float = 0.5,
) -> str | None:
    """During the day: provisional label. After 15:45 finalize; before that never claim final type."""
    if not finalized:
        # provisional hint only — research hook must not treat as final open_type
        return None if abs(gap_pct) < threshold else ("gap-up" if gap_pct > 0 else "gap-down")
    return classify_opening(gap_pct=gap_pct, open_px=open_px, close_px=last_px, threshold=threshold)


@dataclass(frozen=True)
class RiskOffAlarm:
    on: bool
    since_ms: int | None
    reasons: list[str]


def risk_off_alarm(
    *,
    geopolitics_headline: bool,
    brent_chg_pct: float | None,
    vix_chg_pct: float | None,
    within_window: bool,
    brent_thresh: float = 3.0,
    vix_thresh: float = 10.0,
    since_ms: int | None = None,
) -> RiskOffAlarm:
    """All three must hold in the same window (MARKET_INDIA §8b). Information only."""
    reasons: list[str] = []
    if geopolitics_headline:
        reasons.append("geopolitics_headline")
    if brent_chg_pct is not None and brent_chg_pct >= brent_thresh:
        reasons.append(f"brent_+{brent_chg_pct:.1f}%")
    if vix_chg_pct is not None and vix_chg_pct >= vix_thresh:
        reasons.append(f"vix_+{vix_chg_pct:.1f}%")
    on = (
        within_window
        and geopolitics_headline
        and brent_chg_pct is not None
        and brent_chg_pct >= brent_thresh
        and vix_chg_pct is not None
        and vix_chg_pct >= vix_thresh
    )
    return RiskOffAlarm(on=on, since_ms=since_ms if on else None, reasons=reasons if on else [])


def build_morning_brief(
    *,
    trade_date: str,
    built_ms: int,
    cues: list[dict[str, Any]],
    fii_net_cr: float | None,
    dii_net_cr: float | None,
    india_vix: float | None,
    top_headlines: list[dict[str, Any]],
    results_today: list[str],
    events_today: list[str],
    composite: float | None,
) -> dict[str, Any]:
    """Frozen at 08:45 — portal shows this payload, never live-recomputed for that date."""
    by_region: dict[str, list] = {"us": [], "europe": [], "asia": [], "fx_commod": []}
    gift = None
    for c in cues:
        region = c.get("region") or ""
        row = {
            "key": c.get("key"),
            "label": c.get("label"),
            "chg_pct": c.get("chg_pct"),
            "ts_ms": c.get("ts_ms"),
            "stale": bool(c.get("stale")),
        }
        if c.get("key") == "GIFTNIFTY":
            gift = {"chg_pct": c.get("chg_pct"), "ts_ms": c.get("ts_ms"), "stale": True}
        elif region == "us":
            by_region["us"].append(row)
        elif region == "europe":
            by_region["europe"].append(row)
        elif region == "asia":
            by_region["asia"].append(row)
        elif region in {"fx", "commod", "bonds"}:
            by_region["fx_commod"].append(row)
    return {
        "trade_date": trade_date,
        "built_ms": built_ms,
        "gift_nifty": gift,
        "us": by_region["us"],
        "europe": by_region["europe"],
        "asia": by_region["asia"],
        "fx_commod": by_region["fx_commod"],
        "fii_net_cr": fii_net_cr,
        "dii_net_cr": dii_net_cr,
        "india_vix": india_vix,
        "top_headlines": top_headlines[:10],
        "results_today": results_today,
        "events_today": events_today,
        "composite": composite,
    }


def brief_json(brief: dict[str, Any]) -> str:
    return json.dumps(brief, separators=(",", ":"), sort_keys=True)


def signal_opening_features(
    *,
    decision_ms: int,
    gap_pct: float | None,
    imbalance: float | None,
    composite: float | None,
    open_type_final: str | None,
    open_type_finalized_ms: int | None,
    risk_off: bool,
) -> dict[str, Any]:
    """Attach opening context known at decision time only (V1b-6 — no lookahead)."""
    open_type_so_far_val: str | None = None
    if open_type_finalized_ms is not None and decision_ms >= open_type_finalized_ms:
        open_type_so_far_val = open_type_final
    return {
        "gap_pct": gap_pct,
        "imbalance": imbalance,
        "composite": composite,
        "open_type_so_far": open_type_so_far_val,
        "risk_off_alarm": risk_off,
    }
