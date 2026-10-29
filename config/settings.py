"""All engine settings (plan A6). Secrets stay SecretStr; live_orders defaults False."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _force_paper() -> bool:
    """Pytest / CI must never enable live orders even if a .env is present (plan A15)."""
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return True
    return os.environ.get("NSE_FORCE_PAPER", "").lower() in {"1", "true", "yes"}


class Settings(BaseSettings):
    """Env-driven settings. Runtime overrides live in SQLite `settings` via get_setting()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    angel_api_key: SecretStr | None = None
    angel_client_code: SecretStr | None = None
    angel_pin: SecretStr | None = None
    angel_totp_secret: SecretStr | None = None

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    portal_admin_hash: str | None = None
    session_secret: SecretStr | None = None

    mode: Literal["paper", "live"] = "paper"
    live_orders: bool = False
    kill_switch: bool = False

    books_enabled: list[str] = Field(default_factory=lambda: ["A", "B"])
    strategies_enabled: list[str] = Field(default_factory=list)

    capital_inr: float = 100_000.0  # PLAN_V2 D3
    risk_per_trade_pct: float = 1.0
    first_live_risk_pct: float = 0.5
    min_position_inr: float = 100_000.0
    min_position_cnc_inr: float = 20_000.0  # PLAN_V2 D3 / MARKET_INDIA §5
    max_position_pct_capital: float = 300.0
    max_mis_exposure_x: float = 3.0
    max_open_intraday: int = 3
    max_open_swing: int = 4  # R2: ₹25k slots at ₹1L so CNC ₹20k floor clears after floor(qty)
    daily_loss_limit_pct: float = 2.0
    floor_pct: float = 80.0

    broker_squareoff_at: str = "15:10"  # VERIFY Angel app (V1-3)
    squareoff_lead_min: int = 15
    no_entry_lead_min: int = 20
    # Derived at runtime from broker_squareoff_at + leads (defaults match 15:10 → 14:55 / 14:35)
    no_entry_after: str = "14:35"
    square_off_at: str = "14:55"
    trade_special_sessions: bool = False  # Muhurat: no new entries (V1-2)
    book_a_mode: Literal["off", "shadow", "paper"] = "shadow"
    opening_tracker_enabled: bool = True  # D8 — recording only, never a trade filter
    preopen_snapshot_s: int = 30
    cues_poll_s: int = 300
    risk_off_brent_pct: float = 3.0
    risk_off_vix_pct: float = 10.0
    risk_off_window_min: int = 120
    gift_nifty_source: Literal["none", "url", "paid"] = "none"
    max_spread_pct: float = 0.10
    circuit_buffer_pct: float = 2.0
    entry_limit_offset_pct: float = 0.05
    entry_timeout_s: int = 20
    stop_limit_buffer_pct: float = 0.5
    stop_watchdog_s: int = 10
    orders_per_second: int = 5
    history_min_interval_s: float = 0.4
    slippage_pct_mis: float = 0.03
    slippage_pct_cnc: float = 0.05
    ws_mode: int = 3
    tick_stale_alert_s: int = 30

    expected_static_ip: str | None = None
    # Bind loopback by default (PLAN_V2 V0-2 / B24). Nginx or Tailscale publishes the portal.
    web_host: str = "127.0.0.1"
    web_port: int = 8090
    cookie_secure: bool = True  # false only for local plain-HTTP dev / pytest
    # Trust X-Forwarded-Proto / X-Real-IP only when TCP peer is loopback (review R3).
    # Production behind same-host nginx MUST set TRUSTED_PROXY=true.
    trusted_proxy: bool = False
    data_dir: Path = Path("./var")  # runtime only; Python package `data/` is separate
    database_url: str | None = None  # postgres nse_engine — keys live here
    admin_password: SecretStr | None = None  # bootstrap login; prefer PORTAL_ADMIN_HASH

    # Opening + sentiment recorder (PLAN_V2 D8 / §6). RECORDING AND DISPLAY ONLY:
    # nothing here may block, size or time a trade until a pre-registered lab trial shows lift.
    opening_tracker_enabled: bool = True
    preopen_snapshot_s: int = 30
    cues_poll_s: int = 300
    risk_off_brent_pct: float = 3.0
    risk_off_vix_pct: float = 10.0
    risk_off_window_min: int = 120
    gift_nifty_source: Literal["none", "url", "paid"] = "none"  # Q11: proxy until decided

    # News / foreign sentiment (owner 2026-10-23) — off until lab proves lift
    news_filter_enabled: bool = False
    news_block_threshold: float = -0.5

    # Shared crypto infra (docs/SHARED_INFRA.md) — same keys/Space as crypto-signal-engine
    groq_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_model: str = "google/gemma-2-9b-it:free"
    hf_base_url: str | None = None
    hf_space_api_key: SecretStr | None = None
    shared_headlines_path: Path | None = None
    shared_llm_budget_path: Path | None = None
    llm_log_calls: bool = True
    ai_news_review_enabled: bool = False  # optional Groq pass over flagged headlines

    @field_validator("live_orders", mode="after")
    @classmethod
    def _never_live_under_pytest(cls, v: bool) -> bool:
        if _force_paper():
            return False
        return v

    @staticmethod
    def _secret_present(value: SecretStr | None) -> bool:
        return bool(value and value.get_secret_value().strip())

    @property
    def angel_configured(self) -> bool:
        return all(
            self._secret_present(x)
            for x in (
                self.angel_api_key,
                self.angel_client_code,
                self.angel_pin,
                self.angel_totp_secret,
            )
        )


_runtime_overrides: dict[str, Any] = {}
_db_path: Path | None = None


def reset_settings_cache() -> None:
    """Clear cached Settings and runtime overrides (tests)."""
    global _runtime_overrides, _db_path
    _runtime_overrides = {}
    _db_path = None
    get_settings.cache_clear()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def set_runtime_override(key: str, value: Any) -> None:
    """Used by engine/state when the portal writes a runtime setting."""
    _runtime_overrides[key] = value


def get_setting(key: str, default: Any = None) -> Any:
    """Resolve a setting: runtime SQLite override → env Settings → default.

    Keys match Settings field names (plan A6).
    """
    if key in _runtime_overrides:
        return _runtime_overrides[key]
    settings = get_settings()
    if hasattr(settings, key):
        return getattr(settings, key)
    return default
