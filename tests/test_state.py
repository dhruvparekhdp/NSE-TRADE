"""P0-4: migrate empty db; insert/read; second migrate is no-op."""

from __future__ import annotations

from engine.state import (
    append_event,
    get_instrument,
    init_db,
    migrate,
    set_setting,
    upsert_instrument,
)


def test_migrate_empty_and_idempotent(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(db)
    v1 = migrate(conn)
    v2 = migrate(conn)
    assert v1 == v2 == 3  # 001_init + 003_opening (V1b; 002 reserved for V4 paper)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for name in (
        "instruments",
        "sessions",
        "signals",
        "orders",
        "trades",
        "daily_pnl",
        "events",
        "settings",
        "lab_trials",
        "parity",
        "schema_version",
        "morning_brief",
        "global_cues",
        "headlines",
    ):
        assert name in tables
    conn.close()


def test_insert_read_each_core_table(tmp_path):
    conn = init_db(tmp_path / "t.db")
    upsert_instrument(
        conn,
        symbol="SBIN",
        token="3045",
        trading_symbol="SBIN-EQ",
        name="State Bank",
        isin="INE062A01020",
        tick_size=0.05,
        lot_size=1,
        in_universe=1,
        updated_ms=1,
    )
    row = get_instrument(conn, "SBIN")
    assert row is not None
    assert row["token"] == "3045"

    set_setting(conn, "kill_switch", True, updated_by="test")
    val = conn.execute("SELECT value_json FROM settings WHERE key='kill_switch'").fetchone()
    assert val["value_json"] == "true"

    eid = append_event(conn, "test", {"ok": True})
    assert eid >= 1
    conn.close()
