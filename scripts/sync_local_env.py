"""Copy infra + AI keys from crypto .env into local NSE .env (never prints secrets)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

DEFAULT_CRYPTO = Path.home() / "personal/Tennis-bet/crypto-signal-engine/.env"
NSE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NSE = NSE_ROOT / ".env"
DEFAULT_ANGEL = NSE_ROOT / "config" / "angel.env"
ANGEL_KEYS = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET")

COPY_KEYS = (
    "DATABASE_URL",
    "SECRETS_MASTER_KEY",
    "ADMIN_PASSWORD",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_MODEL",
    "OPENROUTER_MODEL",
    "HF_BASE_URL",
    "HF_SPACE_API_KEY",
    "SHARED_HEADLINES_PATH",
    "SHARED_LLM_BUDGET_PATH",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "EXPECTED_STATIC_IP",
)


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _nse_db_url(crypto_url: str) -> str:
    u = urlparse(crypto_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://"))
    return urlunparse((u.scheme, u.netloc, "/nse_engine", u.params, u.query, u.fragment))


def merge_env(crypto: Path, nse: Path) -> list[str]:
    src = _parse(crypto)
    dst = _parse(nse)
    if not src:
        raise FileNotFoundError(f"crypto env missing: {crypto}")
    applied: list[str] = []
    for key in COPY_KEYS:
        val = src.get(key, "")
        if val and not dst.get(key):
            dst[key] = val
            applied.append(key)
    if src.get("DATABASE_URL") and "DATABASE_URL" in applied:
        dst["DATABASE_URL"] = _nse_db_url(src["DATABASE_URL"])
    defaults = {
        "MODE": "paper",
        "LIVE_ORDERS": "false",
        "KILL_SWITCH": "false",
        "DATA_DIR": "./var",
        "WEB_HOST": "127.0.0.1",
        "WEB_PORT": "8090",
        "TZ": "Asia/Kolkata",
        "NEWS_FILTER_ENABLED": "false",
        "LLM_LOG_CALLS": "true",
    }
    for k, v in defaults.items():
        dst.setdefault(k, v)
    lines = [f"{k}={v}" for k, v in sorted(dst.items())]
    nse.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(nse, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return applied


def merge_angel_into_dotenv(angel_path: Path, nse_path: Path) -> list[str]:
    """Overlay ANGEL_* from config/angel.env onto .env for pydantic Settings."""
    src = _parse(angel_path)
    if not src:
        return []
    dst = _parse(nse_path) if nse_path.exists() else {}
    applied: list[str] = []
    for key in ANGEL_KEYS:
        val = src.get(key, "")
        if val:
            dst[key] = val
            applied.append(key)
    if not applied:
        return []
    nse_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in sorted(dst.items())]
    fd = os.open(nse_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return applied


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--crypto", type=Path, default=DEFAULT_CRYPTO)
    p.add_argument("--out", type=Path, default=DEFAULT_NSE)
    p.add_argument("--angel", type=Path, default=DEFAULT_ANGEL)
    args = p.parse_args()
    applied = merge_env(args.crypto, args.out)
    angel = merge_angel_into_dotenv(args.angel, args.out) if args.angel.exists() else []
    print({"out": str(args.out), "merged_keys": applied, "angel_keys": angel, "count": len(applied) + len(angel)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
