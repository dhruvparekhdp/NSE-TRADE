"""Command page vol rank / 200-DMA come from the daily lake via lab.market_filters (same as the scan's F1/F2)."""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from config.settings import reset_settings_cache
from core.clock import IST
from data.lake import Lake
from lab.market_filters import f1_skip_reason, f2_skip_reason, vol_rank_252
from web import portal_data as pd_


def _lake_with_nifty(tmp_path, closes):
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    df = pd.DataFrame({"date": [int(d.strftime("%Y%m%d")) for d in dates], "open": closes, "high": closes,
                       "low": closes, "close": closes, "volume": 1, "source": "bhav"})
    Lake(tmp_path / "lake").write_daily("NIFTYBEES", df)
    return dates[-1]


def test_market_card_matches_scan_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    pd_._NIFTY_FILTERS.clear()
    closes = [100 * math.exp(0.0005 * i + 0.01 * math.sin(i / 3) * (1 + (i > 250))) for i in range(320)]
    last = _lake_with_nifty(tmp_path, closes)
    now_ms = int(datetime(last.year, last.month, last.day, 12, 0, tzinfo=IST).timestamp() * 1000) + 86_400_000
    m = pd_.build_market(None, {"quotes": []}, now_ms)
    assert m["nifty_vol_rank"] == vol_rank_252(closes) and m["nifty_vol_rank"] is not None
    assert m["nifty_above_200dma"] is (f2_skip_reason(closes) is None)
    assert (f1_skip_reason(closes) is not None) == (m["nifty_vol_rank"] > 0.667)


def test_market_card_empty_lake_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    pd_._NIFTY_FILTERS.clear()
    m = pd_.build_market(None, {"quotes": []}, int(datetime(2026, 10, 26, 12, 0, tzinfo=IST).timestamp() * 1000))
    assert m["nifty_vol_rank"] is None and m["nifty_above_200dma"] is None
