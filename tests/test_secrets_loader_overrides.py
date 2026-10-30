"""apply_db_secrets must not wipe the SQLite runtime overrides (market_filter, kill_switch, ...).

30 Oct 2026: the runner calls apply_db_secrets() at start, after init_db loaded the overrides; it called
reset_settings_cache(), which also emptied the overrides, so a saved market_filter="off" read back as "on".
"""

import storage.pg as pg
from config.secrets_loader import apply_db_secrets
from config.settings import get_setting, reset_settings_cache, set_runtime_override


def test_db_secrets_keep_runtime_overrides(monkeypatch):
    reset_settings_cache()
    monkeypatch.setattr(pg, "database_url", lambda: "postgresql://test")
    monkeypatch.setattr(pg, "init_postgres", lambda: None)
    monkeypatch.setattr(pg, "get_app_settings", lambda: {})
    set_runtime_override("market_filter", "off")
    set_runtime_override("kill_switch", True)
    apply_db_secrets()
    assert get_setting("market_filter", "on") == "off"
    assert get_setting("kill_switch", False) is True
    reset_settings_cache()
