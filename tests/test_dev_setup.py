"""NSE-001: one-command setup files, name-only env example, audit baseline."""

from __future__ import annotations

import re
from pathlib import Path

from config.settings import Settings, reset_settings_cache

ROOT = Path(__file__).resolve().parents[1]
_NAME_ONLY = re.compile(r"^(?:#\s*)?([A-Z][A-Z0-9_]*)=$")
# Empty string is safe for these (optional secrets / optional strings).
# Numbers, bools, modes, and paths with defaults stay commented: a blank
# value would override the code default.
_BLANK_OK = {
    "ADMIN_PASSWORD",
    "ANGEL_API_KEY",
    "ANGEL_CLIENT_CODE",
    "ANGEL_PIN",
    "ANGEL_TOTP_SECRET",
    "DATABASE_URL",
    "EXPECTED_STATIC_IP",
    "GROQ_API_KEY",
    "HF_BASE_URL",
    "HF_SPACE_API_KEY",
    "OPENROUTER_API_KEY",
    "PORTAL_ADMIN_HASH",
    "SECRETS_MASTER_KEY",
    "SESSION_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}
_EXTRA_NAMES = {"NSE_BASE", "NSE_FORCE_PAPER", "SECRETS_MASTER_KEY"}
_ADVISORY = re.compile(r"(?:PYSEC-\d{4}-\d+|CVE-\d{4}-\d+|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})")


def _env_example() -> tuple[set[str], set[str]]:
    names: set[str] = set()
    active: set[str] = set()
    for raw in (ROOT / ".env.example").read_text().splitlines():
        line = raw.strip()
        if not line or (line.startswith("#") and "=" not in line):
            continue
        match = _NAME_ONLY.fullmatch(line)
        assert match, f"expected a variable name only, got {line!r}"
        name = match.group(1)
        names.add(name)
        if not line.startswith("#"):
            active.add(name)
    return names, active


def test_makefile_has_setup_lint_typecheck_test_and_audit():
    text = (ROOT / "Makefile").read_text()
    for target in ("setup", "lint", "typecheck", "test", "audit", "secrets", "check", "ci"):
        assert re.search(rf"^{target}:", text, re.M), target
    assert "ruff check ." in text
    assert "-m mypy" in text
    assert "NSE_FORCE_PAPER=1" in text
    assert "LIVE_ORDERS=false" in text
    assert "pip_audit" in text
    assert "security/pip-audit-baseline.txt" in text
    assert "--no-git" in text
    assert "login_check" not in text


def test_dev_requirements_pin_mypy_and_pip_audit():
    text = (ROOT / "requirements-dev.txt").read_text()
    assert "mypy==1.15.0" in text
    assert "pip-audit==2.10.1" in text


def test_env_example_is_names_only_and_keeps_paper_defaults(monkeypatch):
    names, active = _env_example()
    expected = {name.upper() for name in Settings.model_fields}
    missing = expected - names
    assert not missing, sorted(missing)
    unknown = names - expected - _EXTRA_NAMES
    assert not unknown, sorted(unknown)
    assert active == _BLANK_OK
    assert "MODE" not in active
    assert "LIVE_ORDERS" not in active
    for key in active:
        monkeypatch.setenv(key, "")
    reset_settings_cache()
    settings = Settings(_env_file=None)
    assert settings.mode == "paper"
    assert settings.live_orders is False
    assert settings.capital_inr == 100_000.0
    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8090
    assert settings.data_dir == Path("./var")
    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert not settings.angel_configured


def test_pip_audit_baseline_is_an_explicit_id_list():
    lines = [
        line.strip()
        for line in (ROOT / "security/pip-audit-baseline.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines
    assert len(lines) == len(set(lines))
    for line in lines:
        assert _ADVISORY.fullmatch(line), line
