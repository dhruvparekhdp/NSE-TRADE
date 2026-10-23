"""R4: gate fails on empty baselines; research simulates real mirror/random."""

from __future__ import annotations

from core.exits import ExitRules
from core.types import Bar, Signal
from lab.backtest import BTTrade
from lab.baselines import simulate_baselines_from_signals
from lab.evaluate import gate


def _t(ms: int, r: float = 0.2) -> BTTrade:
    return BTTrade(
        symbol="X",
        strategy="S",
        book="B",
        side=1,
        qty=1,
        entry_ms=ms,
        entry_price=100.0,
        stop_init=98.0,
        r_mult=r,
        gross_inr=10.0,
        costs_inr=1.0,
        net_inr=9.0,
        role="pick",
    )


def test_gate_fails_when_baselines_empty():
    picks = [_t(1), _t(2)]
    g = gate("S", picks, [], [], book="B", mid_ms=2)
    assert g.passed is False
    assert "empty_mirrors" in g.reasons
    assert "empty_randoms" in g.reasons


def test_simulate_baselines_from_signals_roles():
    bars = [
        Bar(ts_ms=i * 86_400_000, open=100, high=101, low=99, close=100, volume=1) for i in range(5)
    ]
    pick = Signal(
        ts_ms=bars[1].ts_ms,
        symbol="X",
        side=1,
        entry_ref=100.0,
        stop=98.0,
        target=None,
        time_exit_ms=None,
        strategy="S",
        book="B",
        role="pick",
    )
    from strategies.base import mirror, random_baseline

    sigs = [pick, mirror(pick), random_baseline(pick, bars[0].ts_ms, bars[2].ts_ms)]
    mirrors, randoms = simulate_baselines_from_signals(sigs, bars, ExitRules(product="CNC"))
    # May be empty if no_fill, but roles are filtered — never invent pick as mirror
    assert all(t.role == "mirror" for t in mirrors)
    assert all(t.role == "random" for t in randoms)
