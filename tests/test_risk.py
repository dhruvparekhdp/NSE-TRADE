"""P2-3: each limit returns its reason; min-position rule."""

from __future__ import annotations

from core.risk import PortfolioState, RiskLimits, can_open, size
from core.types import Signal


def _sig(**kw):
    base = dict(
        ts_ms=1,
        symbol="SBIN",
        side=1,
        entry_ref=100.0,
        stop=99.0,
        target=102.0,
        time_exit_ms=None,
        strategy="S1_orb",
        book="A",
    )
    base.update(kw)
    return Signal(**base)


def test_min_position_book_a():
    lim = RiskLimits(min_position_inr=100_000, risk_per_trade_pct=1.0)
    # capital 25k, 1% risk, 1% stop → value ~25k < min
    r = size(100, 99, 25_000, 1.0, 0.05, "A", lim)
    assert r.qty == 0
    assert r.reason == "below_min_position"


def test_kill_switch():
    st = PortfolioState(capital=100_000, start_capital=100_000)
    ok, reason = can_open(st, _sig(), RiskLimits(kill_switch=True), 1)
    assert not ok and reason == "kill_switch"


def test_spread_and_news_filter():
    st = PortfolioState(capital=100_000, start_capital=100_000, spread_pct=0.5, news_score=-0.8)
    ok, reason = can_open(st, _sig(), RiskLimits(max_spread_pct=0.1), 1)
    assert reason == "spread_wide"
    ok, reason = can_open(
        PortfolioState(capital=100_000, start_capital=100_000, news_score=-0.8),
        _sig(),
        RiskLimits(news_filter_enabled=True, news_block_threshold=-0.5),
        1,
    )
    assert reason == "news_risk_off"


def test_symbol_open():
    st = PortfolioState(capital=100_000, start_capital=100_000, open_symbols={"SBIN"})
    ok, reason = can_open(st, _sig(), RiskLimits(), 1)
    assert reason == "symbol_open"
