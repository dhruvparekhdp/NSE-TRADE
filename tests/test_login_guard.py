"""C9: MPIN lockout guard."""

from __future__ import annotations

from engine.login_guard import login_blocked, record_login_result
from engine.state import init_db


def test_blocks_after_two_ab1007_same_key_version(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 1000)
    conn = init_db(tmp_path / "g.db")
    record_login_result(conn, ok=False, error="AB1007 INVALID MPIN")
    assert not login_blocked(conn)
    record_login_result(conn, ok=False, error="AB1007 INVALID MPIN")
    assert login_blocked(conn)


def test_resets_on_key_version_change(tmp_path, monkeypatch):
    conn = init_db(tmp_path / "g.db")
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 1000)
    record_login_result(conn, ok=False, error="AB1007")
    record_login_result(conn, ok=False, error="AB1007")
    assert login_blocked(conn)
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 2000)
    assert not login_blocked(conn)


def test_other_errors_do_not_block(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 1)
    conn = init_db(tmp_path / "g.db")
    record_login_result(conn, ok=False, error="network timeout")
    assert not login_blocked(conn)
