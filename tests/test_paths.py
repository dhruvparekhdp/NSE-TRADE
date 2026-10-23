"""V0-5: research and portal resolve the same db/lake under data_dir."""

from __future__ import annotations

from config.paths import engine_db_path, lake_dir
from config.settings import reset_settings_cache


def test_research_and_portal_share_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_settings_cache()
    assert engine_db_path() == tmp_path / "engine.db"
    assert lake_dir() == tmp_path / "lake"
