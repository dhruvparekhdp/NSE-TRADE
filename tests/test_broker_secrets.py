"""NSE-003: Angel credentials come from one loader and logs do not keep them."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from config.broker_secrets import BrokerSecretsMissing, load_broker_secrets
from config.log_redact import install_log_redaction, redact_message
from config.secrets_report import render_secrets_history
from config.settings import reset_settings_cache

ROOT = Path(__file__).resolve().parents[1]
_ANGEL_READS = (
    "angel_api_key.get_secret_value",
    "angel_client_code.get_secret_value",
    "angel_pin.get_secret_value",
    "angel_totp_secret.get_secret_value",
)


def _set_broker_env(monkeypatch, **overrides: str) -> None:
    values = {
        "ANGEL_API_KEY": "TESTKEY-REDACT-0001",
        "ANGEL_CLIENT_CODE": "CLIENT99",
        "ANGEL_PIN": "9081",
        "ANGEL_TOTP_SECRET": "TESTTOTPSEEDVALUE1",
    }
    values.update(overrides)
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    reset_settings_cache()


def test_missing_broker_secrets_name_fields_and_not_values(monkeypatch):
    _set_broker_env(monkeypatch, ANGEL_API_KEY=None, ANGEL_CLIENT_CODE=None, ANGEL_TOTP_SECRET=None)
    with pytest.raises(BrokerSecretsMissing) as caught:
        load_broker_secrets()
    message = str(caught.value)
    assert "ANGEL_API_KEY" in message
    assert "ANGEL_CLIENT_CODE" in message
    assert "ANGEL_TOTP_SECRET" in message
    assert "ANGEL_PIN" not in message
    assert "9081" not in message


def test_loader_returns_env_values(monkeypatch):
    _set_broker_env(monkeypatch)
    secrets = load_broker_secrets()
    assert secrets.api_key == "TESTKEY-REDACT-0001"
    assert secrets.client_code == "CLIENT99"
    assert secrets.pin == "9081"
    assert secrets.totp_secret == "TESTTOTPSEEDVALUE1"


def test_login_does_not_call_the_broker_when_secrets_are_missing(monkeypatch):
    for name in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    reset_settings_cache()
    from broker.angel import AngelBroker

    called = False

    class Fake:
        def generateSession(self, *_args, **_kwargs):
            nonlocal called
            called = True
            return {"status": True, "data": {}}

    broker = AngelBroker(api=Fake(), totp_now=lambda: "000000")
    with pytest.raises(BrokerSecretsMissing):
        broker.login()
    assert called is False


def test_only_broker_secrets_module_reads_angel_secret_values():
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "tools"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if not any(snippet in text for snippet in _ANGEL_READS):
            continue
        if path.name == "broker_secrets.py":
            continue
        # This test names the forbidden snippets. It is not a reader.
        if path.name == "test_broker_secrets.py":
            continue
        offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_log_redacts_api_key_totp_and_pin(monkeypatch, caplog):
    _set_broker_env(monkeypatch)
    install_log_redaction()
    caplog.set_level(logging.INFO)
    logging.getLogger("nse.test").info(
        "api_key=%s pin=%s totp=%s price=%s",
        "TESTKEY-REDACT-0001",
        "9081",
        "TESTTOTPSEEDVALUE1",
        "9081",
    )
    rendered = caplog.text
    assert "TESTKEY-REDACT-0001" not in rendered
    assert "TESTTOTPSEEDVALUE1" not in rendered
    assert "pin=[REDACTED]" in rendered
    assert "price=9081" in rendered


def test_redact_message_drops_a_stray_seed():
    text = redact_message("seed=TESTTOTPSEEDVALUE1", secrets=["TESTTOTPSEEDVALUE1"])
    assert "TESTTOTPSEEDVALUE1" not in text
    assert "[REDACTED]" in text


def test_secrets_history_report_has_no_values():
    leaked = "SHOULD_NOT_APPEAR_IN_THE_REPORT"
    report = render_secrets_history(
        [
            {
                "file": "config/old.py",
                "commit": "abc123",
                "rule": "generic-api-key",
                "secret": leaked,
                "match": leaked,
            }
        ],
        scanned_at="2026-11-06 18:30 IST",
        gitleaks="gitleaks 8.30.1",
    )
    assert leaked not in report
    assert "config/old.py" in report
    assert "abc123" in report
    assert "generic-api-key" in report
    assert "ROTATE" in report
    empty = render_secrets_history([], scanned_at="2026-11-06 18:30 IST", gitleaks="gitleaks 8.30.1")
    assert "ROTATE" not in empty
    assert "No leaked secrets" in empty
