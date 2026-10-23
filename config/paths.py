"""Single path source: runtime lake/db under settings.data_dir (PLAN_V2 V0-5 / B23)."""

from __future__ import annotations

from pathlib import Path

from config.settings import get_settings


def data_dir() -> Path:
    return Path(get_settings().data_dir)


def lake_dir() -> Path:
    return data_dir() / "lake"


def engine_db_path() -> Path:
    return data_dir() / "engine.db"
