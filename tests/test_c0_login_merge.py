"""C0: merged v-fix-2-login — real session, runner hooks, portal hubs."""

from __future__ import annotations

from pathlib import Path

from engine.runner import EngineRunner

ROOT = Path(__file__).resolve().parents[1]
HUBS = ROOT / "web" / "portal" / "hubs"


def test_angel_session_module_exists():
    import engine.angel_session as mod

    assert callable(mod.angel_login)
    assert callable(mod.refresh_instruments)


def test_portal_hub_files_present():
    for name in ("command.js", "book.js", "evidence.js", "system.js"):
        assert (HUBS / name).is_file(), name


def test_runner_has_real_login_and_instruments():
    r = EngineRunner()
    assert hasattr(r, "_ensure_login")
    src = (Path(__file__).resolve().parents[1] / "engine" / "runner.py").read_text(encoding="utf-8")
    assert "angel_login" in src or "_ensure_login" in src
    assert "refresh_instruments" in src


def test_nav_includes_watchlist_tab():
    nav = (ROOT / "web" / "portal" / "nav.js").read_text(encoding="utf-8")
    assert '"watchlist"' in nav
    assert "Watchlist" in nav
