"""Strategy registry."""
from __future__ import annotations

from strategies.gap import GapAndGo, GapFade
from strategies.intraday_momentum import AfternoonMomo
from strategies.orb import ORB
from strategies.pdh_rs import PDHRS
from strategies.swing_breakout import SwingDonchian, SwingKeltner
from strategies.vwap_revert import VWAPRevert

ALL = {
    s.id: s
    for s in [ORB(), VWAPRevert(), GapFade(), GapAndGo(), AfternoonMomo(), PDHRS(), SwingDonchian(), SwingKeltner()]
}

def get(strategy_id: str):
    return ALL[strategy_id]
