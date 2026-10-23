"""R2: Book B slots must clear the CNC floor; skip reason is not no_fill."""

from __future__ import annotations

import math

from core.risk import RiskLimits, book_b_slot_healthy, size
from core.types import Bar, Signal
from lab.backtest import run_daily_book

# Review probe: four typical swing entries that all died under max_open_swing=5.
_SAMPLES = [
    (150.50, 145.00),
    (2_450.00, 2_360.00),
    (85.25, 82.00),
    (999.95, 970.00),
]


def test_default_max_open_swing_is_four():
    from config.settings import get_settings, reset_settings_cache

    reset_settings_cache()
    assert get_settings().max_open_swing == 4
    assert RiskLimits().max_open_swing == 4


def test_four_sample_trades_size_under_default_limits():
    lim = RiskLimits(max_open_swing=4, min_position_cnc_inr=20_000.0)
    capital = 100_000.0
    for entry, stop in _SAMPLES:
        r = size(entry, stop, capital, 1.0, 0.05, "B", lim)
        assert r.reason == "ok", (entry, stop, r)
        assert r.qty > 0
        assert r.value >= lim.min_position_cnc_inr
        slot = capital / lim.max_open_swing
        assert r.value <= slot + 1e-6


def test_size_never_floors_below_min_when_slot_allows():
    """5 equal slots at ₹1L still reject awkward prices; 4 slots clear the CNC floor."""
    lim5 = RiskLimits(max_open_swing=5, min_position_cnc_inr=20_000.0)
    r5 = size(150.5, 145.0, 100_000.0, 1.0, 0.05, "B", lim5)
    slot5 = 20_000.0
    floored = int(slot5 / 150.5) * 150.5
    assert floored < 20_000
    assert math.ceil(20_000 / 150.5) * 150.5 > slot5
    assert r5.qty == 0 and r5.reason == "below_min_cnc_position"
    lim4 = RiskLimits(max_open_swing=4, min_position_cnc_inr=20_000.0)
    r4 = size(150.5, 145.0, 100_000.0, 1.0, 0.05, "B", lim4)
    assert r4.reason == "ok" and r4.value >= 20_000


def test_slot_health_check():
    assert book_b_slot_healthy(100_000.0, 4, 20_000.0) is True
    assert book_b_slot_healthy(100_000.0, 5, 20_000.0) is False  # 20k < 1.1*20k
    assert book_b_slot_healthy(100_000.0, 4, 25_000.0) is False


def test_backtest_records_below_min_not_no_fill():
    """When size refuses, the signal is skipped with the real reason — not no_fill."""

    class AlwaysSignal:
        id = "T_size"
        book = "B"
        timeframe = "1d"

        def on_bar(self, symbol: str, bars, ctx):  # noqa: ANN001
            closed = bars.closed()
            if len(closed) < 2:
                return []
            b = closed[-1]
            return [
                Signal(
                    ts_ms=b.ts_ms,
                    symbol=symbol,
                    side=1,
                    entry_ref=b.close,
                    stop=b.close * 0.99,
                    target=None,
                    time_exit_ms=None,
                    strategy=self.id,
                    book="B",
                    role="pick",
                    features={},
                )
            ]

    # Tiny capital → slot under CNC floor → size refuses after a fillable next day
    bars = [
        Bar(ts_ms=i * 86_400_000, open=100, high=101, low=99, close=100, volume=1)
        for i in range(5)
    ]
    lim = RiskLimits(max_open_swing=4, min_position_cnc_inr=20_000.0, risk_per_trade_pct=1.0)
    bt = run_daily_book(
        symbol="X",
        daily_bars=bars,
        strategy=AlwaysSignal(),
        capital=10_000.0,
        limits=lim,
    )
    assert bt.no_fills == []
    skipped = [s for s in bt.signals if (s.features or {}).get("skip_reason") == "below_min_cnc_position"]
    assert skipped, "expected below_min_cnc_position skip_reason on signals"
