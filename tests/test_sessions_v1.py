"""V1-1: dated session regimes per stock class (MARKET_INDIA §2)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.clock import SessionState, session_state

IST = ZoneInfo("Asia/Kolkata")


def _ms(y: int, m: int, d: int, hh: int, mm: int) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=IST).timestamp() * 1000)


def test_fo_cas_window_oct_2026():
    # 23 Oct 2026 15:20 IST — F&O in CAS (3 Aug–6 Dec regime)
    assert session_state(_ms(2026, 10, 23, 15, 20), stock_class="fo") == SessionState.CLOSING_AUCTION


def test_fo_continuous_after_7_dec_2026():
    # 8 Dec 2026 15:20 — continuous until 15:30; keep square-off after that for this probe
    assert (
        session_state(
            _ms(2026, 12, 8, 15, 20),
            stock_class="fo",
            square_off_at="15:28",
            no_entry_after="15:25",
        )
        == SessionState.OPEN
    )


def test_non_fo_still_open_at_1520_oct():
    assert (
        session_state(
            _ms(2026, 10, 23, 15, 20),
            stock_class="non_fo",
            square_off_at="15:28",
            no_entry_after="15:25",
        )
        == SessionState.OPEN
    )


def test_pre_open_0909():
    assert session_state(_ms(2026, 10, 23, 9, 9), stock_class="fo") == SessionState.PRE_OPEN


def test_muhurat_afternoon_8_nov():
    # Muhurat continuous 14:20–15:15 → SPECIAL/OPEN-like (MUHURAT or OPEN)
    st = session_state(_ms(2026, 11, 8, 14, 30), stock_class="fo")
    assert st in {SessionState.MUHURAT, SessionState.SPECIAL, SessionState.OPEN}
