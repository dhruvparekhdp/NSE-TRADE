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


def test_streak_carries_over_to_the_next_day_while_key_unchanged(tmp_path, monkeypatch):
    """Angel's 5-strike MPIN lock is not daily; a block from yesterday must hold today."""
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 1000)
    conn = init_db(tmp_path / "g.db")
    conn.execute(
        "INSERT INTO login_guard(day, key_version_ms, ab1007_streak, blocked) VALUES ('2000-01-01', 1000, 2, 1)"
    )
    conn.commit()
    assert login_blocked(conn)
    monkeypatch.setattr("engine.login_guard.secrets_key_version_ms", lambda: 2000)
    assert not login_blocked(conn)


def test_key_version_reads_tuple_rows(monkeypatch):
    """storage.pg.connect returns tuple rows; the version must not silently fall back to 0."""
    import engine.login_guard as lg

    class _Cur:
        def fetchone(self):
            return (1_793_000_000_000.0,)

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **k):
            return _Cur()

    monkeypatch.setattr("storage.pg.database_url", lambda: "postgresql://x")
    monkeypatch.setattr("storage.pg.connect", lambda url=None: _Conn())
    assert lg.secrets_key_version_ms() == 1_793_000_000_000
