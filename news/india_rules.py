"""India + macro headline rules (crypto-style event tags, equity universe)."""

from __future__ import annotations

import re

EVENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("rbi_policy", ("rbi", "repo rate", "mpc ", "monetary policy", "reverse repo")),
    ("budget", ("union budget", "budget 20", "finance minister", "fiscal deficit")),
    ("sebi", ("sebi", "f&o ban", "derivative", "margin rules")),
    ("election", ("election", "lok sabha", "exit poll", "modi", "bjp", "congress wins")),
    ("war", ("war", "missile", "invasion", "airstrike", "sanction")),
    ("geopolitics_india", ("border clash", "loc fire", "pakistan army", "china border", "ladakh", "doklam")),
    ("middle_east", ("iran", "israel", "red sea", "hormuz", "houthi", "gaza")),
    ("russia_ukraine", ("ukraine", "russia invasion", "kyiv", "moscow strike")),
    ("tariffs_trade", ("tariff", "trade deal", "trade war", "import duty")),
    ("us_data", ("nonfarm", "payrolls", "us cpi", "us gdp", "ism manufacturing")),
    ("china", ("china gdp", "pboc", "yuan ", "evergrande", "beijing stimulus")),
    ("opec", ("opec", "oil cut", "oil production quota")),
    ("monsoon", ("monsoon", "imd forecast", "rainfall deficit")),
    ("gst_council", ("gst council", "gst rate cut", "gst rate hike")),
    ("india_macro", ("iip ", "india gdp", "india cpi", "fiscal deficit print")),
    ("block_deal", ("block deal", "bulk deal")),
    ("promoter_pledge", ("promoter pledge", "share pledge", "pledged shares")),
    ("fed", ("fomc", "fed ", "powell", "rate cut", "rate hike", "us rates")),
    ("inflation", ("cpi", "wpi", "inflation", "gst rate")),
    ("earnings", ("results", "q1 ", "q2 ", "q3 ", "q4 ", "net profit", "pat ", "earnings")),
    ("fii_dii", ("fii", "dii", "foreign fund", "institutional investor")),
    ("credit_rating", ("moody", "fitch", "s&p", "downgrade", "upgrade rating")),
    ("banking_stress", ("fraud", "npcil", "npa", "write-off", "raid", "ed attaches")),
    ("commodity", ("crude", "brent", "gold hits", "oil price")),
]

NOISE = re.compile(
    r"price prediction|should you buy|technical analysis|newsletter|what to expect|tips for",
    re.I,
)

# Common Nifty names → symbol hints (extend over time)
NAMES: dict[str, tuple[str, ...]] = {
    "RELIANCE": ("reliance", "ril"),
    "TCS": ("tcs", "tata consultancy"),
    "INFY": ("infosys", "infy"),
    "HDFCBANK": ("hdfc bank", "hdfcbank"),
    "ICICIBANK": ("icici bank", "icicibank"),
    "SBIN": ("sbi ", "state bank"),
    "BHARTIARTL": ("airtel", "bharti"),
    "ITC": (" itc ",),
    "LT": ("larsen", "l&t"),
    "AXISBANK": ("axis bank",),
    "EMUDHRA": ("emudhra", "e-mudra", "emudhra"),
}


def event_type(headline: str) -> str:
    h = " " + headline.lower() + " "
    if NOISE.search(h):
        return "noise"
    for name, words in EVENT_RULES:
        if any(w in h for w in words):
            return name
    return "other"


def symbol_hint(headline: str) -> str:
    h = " " + headline.lower() + " "
    hits = [sym for sym, names in NAMES.items() if any(n in h for n in names)]
    return hits[0] if len(hits) == 1 else "MARKET"


def score_from_probs(probs: dict, headline: str) -> dict:
    """FinBERT probs + India rules → score/confidence/event/symbol."""
    ev = event_type(headline)
    pos = float(probs.get("positive", 0) or probs.get("pos", 0) or 0)
    neg = float(probs.get("negative", 0) or probs.get("neg", 0) or 0)
    score = pos - neg
    conf = max(pos, neg, 0.0)
    if ev == "noise":
        score, conf = 0.0, min(conf, 0.1)
    if ev in {"war", "banking_stress", "credit_rating"} and score > -0.2:
        score = min(score, -0.25)
    if ev == "fii_dii" and "outflow" in headline.lower():
        score = min(score, -0.3)
    if ev == "fii_dii" and "inflow" in headline.lower():
        score = max(score, 0.3)
    return {
        "score": round(max(-1.0, min(1.0, score)), 3),
        "confidence": round(max(0.0, min(1.0, conf)), 3),
        "event_type": ev,
        "symbol": symbol_hint(headline),
    }
