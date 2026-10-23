"""R13: daily book trail uses ATR14 from bars, not entry stop/2.5."""

from __future__ import annotations

from core.indicators import atr
from core.types import Bar


def test_atr14_changes_with_new_bar():
    bars = [
        Bar(ts_ms=i, open=100 + i * 0.1, high=101 + i * 0.1, low=99, close=100 + i * 0.1, volume=1000)
        for i in range(20)
    ]
    hs = [b.high for b in bars]
    ls = [b.low for b in bars]
    cs = [b.close for b in bars]
    a1 = atr(hs[:15], ls[:15], cs[:15], 14)[-1]
    a2 = atr(hs, ls, cs, 14)[-1]
    assert a1 is not None and a2 is not None
    assert a2 != a1 or len(bars) == 15
