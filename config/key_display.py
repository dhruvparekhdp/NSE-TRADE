"""Masked key previews + keyed fingerprints (PLAN_V2 V0-8). Never log raw values."""

from __future__ import annotations

import hashlib
import hmac
import os


def mask_value(value: str, *, kind: str = "secret", key: str = "") -> str:
    """first2 + ••• + last2; MPIN / short values → •••• only."""
    if not value:
        return ""
    if key == "angel_pin" or kind == "secret" and len(value) < 8:
        return "••••"
    if len(value) <= 4:
        return "••••"
    return value[:2] + "•••" + value[-2:]


def fingerprint(value: str, *, key: str = "") -> str | None:
    """12-char HMAC-SHA256 with SECRETS_MASTER_KEY. None for MPIN / values under 8 chars."""
    if not value or key == "angel_pin" or len(value) < 8:
        return None
    master = os.environ.get("SECRETS_MASTER_KEY", "").strip() or "nse-dev-no-master"
    digest = hmac.new(master.encode(), value.encode(), hashlib.sha256).hexdigest()
    return digest[:12]


def first_diff_at(a: str, b: str) -> int | None:
    """0-based index of first differing character, or None if equal."""
    if a == b:
        return None
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n
