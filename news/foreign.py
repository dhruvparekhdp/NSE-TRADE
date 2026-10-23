"""Foreign / macro feature builders from already-fetched series (tests: no network)."""

from __future__ import annotations

from news.sentiment import SentimentSnapshot, composite_score, score_headlines


def build_snapshot(
    *,
    trade_date: str,
    us_close_yesterday: float | None = None,
    us_close_day_before: float | None = None,
    usdinr_today: float | None = None,
    usdinr_yesterday: float | None = None,
    india_vix: float | None = None,
    india_vix_yesterday: float | None = None,
    fii_net_cr: float | None = None,
    dii_net_cr: float | None = None,
    headlines: list[str] | None = None,
    results_window: bool = False,
) -> tuple[SentimentSnapshot, float]:
    us_ret = None
    if us_close_yesterday and us_close_day_before and us_close_day_before > 0:
        us_ret = (us_close_yesterday - us_close_day_before) / us_close_day_before * 100.0
    usd_chg = None
    if usdinr_today and usdinr_yesterday and usdinr_yesterday > 0:
        usd_chg = (usdinr_today - usdinr_yesterday) / usdinr_yesterday * 100.0
    vix_chg = None
    if india_vix is not None and india_vix_yesterday is not None:
        vix_chg = india_vix - india_vix_yesterday
    snap = SentimentSnapshot(
        trade_date=trade_date,
        us_overnight_pct=us_ret,
        usdinr_chg_pct=usd_chg,
        india_vix=india_vix,
        india_vix_chg=vix_chg,
        fii_net_cr=fii_net_cr,
        dii_net_cr=dii_net_cr,
        headline_score=score_headlines(headlines or []),
        results_window=results_window,
    )
    return snap, composite_score(snap)
