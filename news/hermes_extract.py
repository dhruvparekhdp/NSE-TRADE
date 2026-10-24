"""Structured event fields from headlines — rules first, optional LLM (SHARED_INFRA)."""

from __future__ import annotations

from typing import Any

from news.india_rules import event_type, score_from_probs, symbol_hint
from news.sentiment import score_headlines

_EXTRACT_SYSTEM = """You extract Indian equity news events. Reply with JSON only:
{"symbols":["SYM"],"event_type":"snake_case","severity":-1..1,"summary":"one line","is_company_specific":true|false}
Use NSE symbols when known; empty symbols if market-wide. severity: negative bad for holders."""

_CYBER_WORDS = ("security breach", "data breach", "cyber", "hacked", "vulnerability", "security lapse")


def _rules_event_type(headline: str) -> str:
    ev = event_type(headline)
    h = headline.lower()
    if any(w in h for w in _CYBER_WORDS):
        return "cyber_breach"
    return ev


def _rules_symbols(headline: str, extra_names: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    from news.india_rules import NAMES

    names = dict(NAMES)
    if extra_names:
        names.update(extra_names)
    h = " " + headline.lower() + " "
    hits = [sym for sym, tokens in names.items() if any(n in h for n in tokens)]
    if hits:
        return hits[:3]
    hint = symbol_hint(headline)
    return [] if hint == "MARKET" else [hint]


def extract_from_rules(headline: str, extra_names: dict[str, tuple[str, ...]] | None = None) -> dict[str, Any]:
    """Deterministic extract for tests and LLM-off production."""
    ev = _rules_event_type(headline)
    tag = score_headlines([headline])
    probs = {"positive": max(0, tag), "negative": max(0, -tag), "neutral": 1 - abs(tag)}
    scored = score_from_probs(probs, headline)
    symbols = _rules_symbols(headline, extra_names=extra_names)
    severity = float(scored["score"])
    if ev == "cyber_breach" and severity > -0.3:
        severity = -0.55
    company = bool(symbols) and ev not in {"fed", "us_data", "budget", "rbi_policy", "other", "noise"}
    return {
        "symbols": symbols,
        "event_type": ev,
        "severity": round(max(-1.0, min(1.0, severity)), 3),
        "summary": headline.strip()[:240],
        "is_company_specific": company,
        "source": "rules",
        "confidence": scored["confidence"],
    }


def merge_llm(rules: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    """Prefer LLM symbols/event_type when present; keep rules severity if LLM omits."""
    out = dict(rules)
    out["source"] = "llm+rules"
    for key in ("symbols", "event_type", "summary", "is_company_specific"):
        if key in llm and llm[key] not in (None, "", []):
            out[key] = llm[key]
    if "severity" in llm and isinstance(llm["severity"], int | float):
        out["severity"] = round(max(-1.0, min(1.0, float(llm["severity"]))), 3)
    syms = out.get("symbols") or []
    if isinstance(syms, str):
        out["symbols"] = [syms.upper()]
    else:
        out["symbols"] = [str(s).upper() for s in syms if s][:5]
    return out


def extract_event(
    headline: str,
    *,
    use_llm: bool = False,
    extra_names: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Rules extract; optional ask_json when use_llm and keys configured."""
    rules = extract_from_rules(headline, extra_names=extra_names)
    if not use_llm:
        return rules
    from integrations.llm_client import ask_json

    reply = ask_json(
        "news_event",
        _EXTRACT_SYSTEM,
        f"Headline: {headline}",
    )
    if reply is None:
        return rules
    try:
        return merge_llm(rules, reply.data)
    except (TypeError, ValueError):
        return rules
