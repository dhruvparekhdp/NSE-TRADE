"""Plain-English text for every machine reason the engine can give (PLAN_V2 §7, V5-2).

WHY: signals and refused orders carry short machine codes (``near_circuit``, ``max_open_swing``). The
portal shows the sentence, never the code, so the owner can read "why refused" on a phone. One dict is
the single source: ``core/risk.py`` codes, the V1/V3/V4 codes the plan adds, and the outcome codes.
A code nobody wrote text for is shown humanised ("some new code") rather than hidden, and a test
fails when ``core/risk.py`` gains a reason that has no sentence here.
"""

from __future__ import annotations

# {min_position} is filled from settings (default ₹20,000: PLAN_V2 D3).
REASONS: dict[str, str] = {
    # core/risk.py (PLAN A9.3)
    "kill_switch": "kill switch is on: no new entries",
    "floor": "wallet fell to the floor: trading is paused",
    "daily_loss_limit": "today's loss limit was reached",
    "session_closed": "market session is not open for new entries",
    "max_open_intraday": "too many intraday positions open already",
    "max_open_swing": "swing book is full: maximum open positions reached",
    "sector_cap": "already two swing positions open in this sector",
    "market_filter_f1_vol": "Nifty volatility in the top third of the past year",
    "market_filter_f2_trend": "Nifty below its 200-day average",
    "mis_exposure": "intraday exposure is at its cap",
    "symbol_open": "already holding this stock",
    "already_in_symbol": "another strategy already queued or holds this stock",
    "cash": "not enough cash for this buy and its charges",
    "spread_wide": "bid-ask spread too wide to trade cheaply",
    "near_circuit": "too close to today's price band",
    "results_day": "results due within 3 days",
    "news_risk_off": "bad news flow: long entries blocked",
    "news_risk_on_short_block": "strongly good news flow: short entries blocked",
    # sizing and costs (V1-4 / V1-5)
    "qty_zero": "risk budget buys less than one share",
    "below_min_position": "position under ₹{min_position}: costs would eat too much",
    "below_min_cnc_position": "position under ₹{min_position}: costs would eat too much",
    "surveillance": "stock is on the exchange's surveillance (ASM/GSM) list",
    "not_in_universe": "stock is not in today's trading universe",
    "series_not_eq": "stock is not in the plain EQ series",
    # market filter and session (V1 / V3)
    "market_filter": "Nifty volatility in the top third of the past year",
    "calendar_missing": "no holiday calendar for this year: trading jobs are skipped",
    "special_session": "special session (Muhurat): no new entries",
    "holiday": "exchange holiday",
    "stale_data": "price data is stale",
    # paper broker and fills (V4)
    "insufficient_funds": "not enough cash for this position and its costs",
    "no_fill": "price never reached the entry limit",
    "short_not_allowed": "delivery (CNC) book is long only",
    "sell_same_day": "shares bought today cannot be sold today",
    # book A shadow and baselines
    "shadow": "intraday book is shadow only: logged, not traded",
    "book_a_shadow": "intraday book is shadow only: logged, not traded",
    "mirror": "mirror baseline: opposite side, recorded for comparison only",
    "random": "random baseline: recorded for comparison only",
    "paper_disabled": "paper trading is not switched on",
    # exits
    "stop": "stop-loss hit",
    "trail": "trailing stop hit",
    "time_limit": "20-session time limit reached",
    "square_off": "intraday square-off",
    "target": "target hit",
    "gap_stop": "opened beyond the stop: filled at the open",
}

DEFAULT_MIN_POSITION_INR = 20_000


def reason_text(code: str | None, *, min_position_inr: float | None = None) -> str:
    """Sentence for a machine reason. Empty code -> empty string; unknown code -> humanised code."""
    if not code:
        return ""
    template = REASONS.get(str(code))
    if template is None:
        return str(code).replace("_", " ").strip()
    amount = min_position_inr if min_position_inr else DEFAULT_MIN_POSITION_INR
    return template.format(min_position=f"{amount:,.0f}")
