"""PLAN_V2 V1b-1..V1b-6 opening / sentiment recorder tests."""

from __future__ import annotations

from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from data.flows import parse_fii_dii
from data.global_cues import CueSpec, load_cue_specs, parse_yahoo_chart
from data.preopen import mark_final, parse_preopen_payload
from engine.opening import classify_opening, risk_off_alarm, signal_opening_features
from engine.state import init_db
from news.headlines_store import HeadlineIn, dedupe_batch, external_id_for
from news.india_rules import event_type
from web.app import create_app


def test_v1b_1_cues_stale_closed_market():
    specs = load_cue_specs()
    assert any(s.key == "SPX" and s.symbol == "^GSPC" for s in specs)
    gift = next(s for s in specs if s.key == "GIFTNIFTY")
    assert gift.symbol is None
    # Live quote within interval → not stale
    live = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 5000.0,
                        "regularMarketTime": 1_700_000_000,
                        "previousClose": 4900.0,
                        "gmtoffset": 0,
                    },
                    "timestamp": [1_700_000_000 - 86_400, 1_700_000_000],
                    "indicators": {"quote": [{"close": [4900.0, 5000.0]}]},
                }
            ]
        }
    }
    row = parse_yahoo_chart(
        live,
        CueSpec("SPX", "S&P", "us", "^GSPC", "yahoo"),
        now_ms=1_700_000_000_000 + 60_000,
        interval_s=300,
    )
    assert row is not None and row.stale is False and row.chg_pct is not None
    # Old market time → stale (closed), chg still real not 0
    stale_row = parse_yahoo_chart(
        live,
        CueSpec("SPX", "S&P", "us", "^GSPC", "yahoo"),
        now_ms=1_700_000_000_000 + 3_600_000,
        interval_s=300,
    )
    assert stale_row is not None and stale_row.stale is True and stale_row.chg_pct != 0


def test_v1b_1_flows_fixture():
    payload = [
        {"category": "FII/FPI", "netValue": "-1,200.50", "date": "23-Oct-2026"},
        {"category": "DII", "netValue": "800.00", "date": "23-Oct-2026"},
    ]
    d = parse_fii_dii(payload)
    assert d is not None
    assert d.trade_date == "2026-10-23"
    assert d.fii_net_cr == -1200.5 and d.dii_net_cr == 800.0


def test_v1b_2_preopen_final():
    raw = {
        "data": [
            {
                "symbol": "NIFTY",
                "iep": 25000.0,
                "prev_close": 24800.0,
                "buy_qty": 1200,
                "sell_qty": 800,
            }
        ]
    }
    snaps = parse_preopen_payload(raw, trade_date="2026-10-23", ts_ms=1)
    assert snaps[0].chg_pct is not None
    assert snaps[0].imbalance == 0.2
    assert mark_final(snaps)[0].final is True


def test_v1b_3_tags_and_dedupe():
    assert event_type("India Pakistan border clash overnight") == "geopolitics_india"
    assert event_type("Red Sea attacks lift Hormuz risk") == "middle_east"
    assert event_type("OPEC agrees oil production cut") == "opec"
    assert event_type("GST Council cuts rates on durables") == "gst_council"
    a = HeadlineIn("et", "RBI holds repo rate", "http://x/1", 1, 1, "rbi_policy", "MARKET", 0.0, 0.5)
    b = HeadlineIn("et", "RBI holds repo rate", "http://x/1", 1, 1, "rbi_policy", "MARKET", 0.0, 0.5)
    c = HeadlineIn("mc", "RBI holds repo rate today", None, 1, 2, "rbi_policy", "MARKET", 0.0, 0.5)
    assert len(dedupe_batch([a, b, c])) == 1
    assert external_id_for(source="et", link="http://x/1", title="t") == "et:http://x/1"


def test_v1b_4_opening_types_and_risk_off():
    assert classify_opening(gap_pct=0.8, open_px=100, close_px=101) == "gap-up-and-go"
    assert classify_opening(gap_pct=0.8, open_px=100, close_px=99) == "gap-up-fade"
    assert classify_opening(gap_pct=-0.8, open_px=100, close_px=101) == "gap-down-recover"
    assert classify_opening(gap_pct=-0.8, open_px=100, close_px=99) == "gap-down-go"
    assert classify_opening(gap_pct=0.1, open_px=100, close_px=99) == "flat"
    assert risk_off_alarm(
        geopolitics_headline=True, brent_chg_pct=3.5, vix_chg_pct=12.0, within_window=True
    ).on is True
    assert risk_off_alarm(
        geopolitics_headline=True, brent_chg_pct=3.5, vix_chg_pct=5.0, within_window=True
    ).on is False


def test_v1b_6_no_lookahead_open_type():
    feats = signal_opening_features(
        decision_ms=10 * 3600 * 1000,
        gap_pct=0.7,
        imbalance=0.1,
        composite=0.2,
        open_type_final="gap-up-and-go",
        open_type_finalized_ms=15 * 3600 * 1000 + 45 * 60 * 1000,
        risk_off=False,
    )
    assert feats["open_type_so_far"] is None
    feats2 = signal_opening_features(
        decision_ms=16 * 3600 * 1000,
        gap_pct=0.7,
        imbalance=0.1,
        composite=0.2,
        open_type_final="gap-up-and-go",
        open_type_finalized_ms=15 * 3600 * 1000 + 45 * 60 * 1000,
        risk_off=False,
    )
    assert feats2["open_type_so_far"] == "gap-up-and-go"


async def test_v1b_5_api_empty_contract(tmp_path: Path):
    db = init_db(tmp_path / "t.db")
    app = create_app(db=db)
    async with TestClient(TestServer(app)) as client:
        for path in ("/api/opening", "/api/sentiment", "/api/headlines"):
            resp = await client.get(path)
            assert resp.status == 200
            assert isinstance(await resp.json(), dict)
        opening = await (await client.get("/api/opening")).json()
        assert "trade_date" in opening and "brief" in opening and "preopen" in opening
        sent = await (await client.get("/api/sentiment")).json()
        assert "composite" in sent and "risk_off_alarm" in sent
        hl = await (await client.get("/api/headlines")).json()
        assert "rows" in hl and "tags" in hl
