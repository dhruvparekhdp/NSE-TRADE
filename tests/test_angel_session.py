"""F1e/F1f: instrument refresh from the scrip master and the daily Angel login (no network)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from engine.angel_session import (
    AngelCandleClient,
    angel_login,
    iter_json_array,
    record_session,
    refresh_instruments,
)
from engine.state import init_db

CSV = "Company Name,Industry,Symbol,Series,ISIN Code\nState Bank,Financial Services,SBIN,EQ,INE062A01020\nTCS Ltd,Information Technology,TCS,EQ,INE467B01029\nGone Ltd,Services,GONE,EQ,INE000000000\n"  # noqa: E501
SCRIP = json.dumps([
    {"token": "3045", "symbol": "SBIN-EQ", "name": "SBIN", "exch_seg": "NSE", "tick_size": "5.000000", "lotsize": "1", "instrumenttype": ""},  # noqa: E501
    {"token": "11536", "symbol": "TCS-EQ", "name": "TCS", "exch_seg": "NSE", "tick_size": "10.000000", "lotsize": "1", "instrumenttype": ""},  # noqa: E501
    {"token": "99926000", "symbol": "Nifty 50", "name": "NIFTY", "exch_seg": "NSE", "tick_size": "0", "lotsize": "1", "instrumenttype": "AMXIDX"},  # noqa: E501
    {"token": "1", "symbol": "SBIN26NOVFUT", "name": "SBIN", "exch_seg": "NFO", "tick_size": "10", "lotsize": "750", "instrumenttype": "FUTSTK"},  # noqa: E501
])


def test_iter_json_array_streams_every_object():
    assert [r["token"] for r in iter_json_array(SCRIP)] == ["3045", "11536", "99926000", "1"]


def test_refresh_instruments_maps_universe_ticks_and_index(tmp_path):
    conn = init_db(tmp_path / "e.db")
    conn.execute("INSERT INTO instruments(symbol, token, in_universe, updated_ms) VALUES ('OLDNAME', '9', 1, 0)")
    stats = refresh_instruments(conn, SCRIP, CSV)
    assert stats == {"universe": 2, "missing": ["GONE"], "index_token": True}
    rows = {r["symbol"]: dict(r) for r in conn.execute("SELECT * FROM instruments")}
    assert rows["SBIN"]["token"] == "3045" and rows["SBIN"]["tick_size"] == 0.05 and rows["SBIN"]["in_universe"] == 1
    assert rows["TCS"]["tick_size"] == 0.1
    assert rows["NIFTY 50"]["token"] == "99926000" and rows["NIFTY 50"]["in_universe"] == 0
    assert rows["OLDNAME"]["in_universe"] == 0  # names that left the index leave the universe


def _settings(**over):
    base = dict(angel_configured=True, angel_totp_secret=SecretStr(" jbsw y3dp "), angel_client_code=SecretStr("A1 "),
                angel_pin=SecretStr("1234"))
    base.update(over)
    return SimpleNamespace(**base)


class FakeApi:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def generateSession(self, code, pin, totp):  # noqa: N802 — SDK name
        self.calls.append((code, pin, totp))
        return {"status": True} if self.ok else {"status": False, "errorcode": "AB1050", "message": "Invalid totp"}

    def getCandleData(self, payload):  # noqa: N802
        return {"status": True, "data": [["2026-10-23T00:00:00+05:30", 1, 2, 0.5, 1.5, 10]]}


def test_login_normalises_secret_and_uses_utc_totp():
    api = FakeApi()
    seen = []
    out = angel_login(_settings(), build_api=lambda: api, totp_fn=lambda s: seen.append(s) or "123456")
    assert out is api and seen == ["JBSWY3DP"] and api.calls == [("A1", "1234", "123456")]


def test_login_failure_raises_with_angel_code():
    with pytest.raises(RuntimeError, match="AB1050"):
        angel_login(_settings(), build_api=lambda: FakeApi(ok=False), totp_fn=lambda s: "000000")
    with pytest.raises(RuntimeError, match="not configured"):
        angel_login(_settings(angel_configured=False))


def test_candle_client_returns_rows_and_records_session(tmp_path):
    assert AngelCandleClient(FakeApi()).get_candle_data({})[0][4] == 1.5
    conn = init_db(tmp_path / "e.db")
    record_session(conn, date(2026, 10, 26), False, "AB1050 Invalid totp")
    record_session(conn, date(2026, 10, 26), True)
    row = conn.execute("SELECT login_ok, error FROM sessions WHERE trade_date='2026-10-26'").fetchone()
    assert row["login_ok"] == 1 and row["error"] is None
