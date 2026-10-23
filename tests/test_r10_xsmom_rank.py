"""R10: S7 cross-sectional z-score rank and top-N / top-2N exit."""

from __future__ import annotations

from strategies.xsmom_rank import exit_symbols, momentum_score, pick_symbols, rank_universe


def _uptrend(n: int, start: float = 100.0) -> list[float]:
    out = [start]
    for _ in range(n - 1):
        out.append(out[-1] * 1.002)
    return out


def test_rank_orders_strongest_first():
    u = {"A": _uptrend(260, 100), "B": _uptrend(260, 50), "C": _uptrend(260, 80)}
    ranked = rank_universe(u)
    assert ranked[0][0] == "A"
    assert ranked[0][1] > ranked[-1][1]


def test_pick_and_exit_top_2n():
    ranked = [("A", 1.0), ("B", 0.5), ("C", 0.2), ("D", -0.1)]
    picks = pick_symbols(ranked, capital=100_000, min_position_cnc_inr=25_000)
    assert picks == {"A", "B", "C", "D"}
    ranked5 = [("A", 1), ("B", 0.9), ("C", 0.8), ("D", 0.1), ("E", -0.2)]
    assert "E" in exit_symbols(ranked5, {"E"}, capital=50_000, min_position_cnc_inr=25_000)
    assert not exit_symbols(ranked5, {"D"}, capital=50_000, min_position_cnc_inr=25_000)


def test_momentum_score_needs_252_bars():
    assert momentum_score(_uptrend(200)) is None
    assert momentum_score(_uptrend(252)) is not None
