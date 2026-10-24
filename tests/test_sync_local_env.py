"""sync_local_env merges without clobbering existing keys."""

from __future__ import annotations

from pathlib import Path

from scripts.sync_local_env import merge_env


def test_merge_env_preserves_existing(tmp_path: Path):
    crypto = tmp_path / "crypto.env"
    nse = tmp_path / "nse.env"
    crypto.write_text("GROQ_API_KEY=from_crypto\nDATABASE_URL=postgresql://u:p@h/db\n", encoding="utf-8")
    nse.write_text("GROQ_API_KEY=keep_me\n", encoding="utf-8")
    applied = merge_env(crypto, nse)
    text = nse.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=keep_me" in text
    assert "DATABASE_URL=" in text
    assert "DATABASE_URL" in applied
