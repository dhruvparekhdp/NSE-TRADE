"""Plain-English Angel error hints (PLAN_V2 V0-6)."""

from __future__ import annotations

HINTS: dict[str, str] = {
    "AB1050": "TOTP secret doesn't match this client code: re-enable TOTP and save the new secret",
    "AB1001": "Invalid credentials — check client code / MPIN",
    "AB1000": "Session expired — try Test Angel again",
}


def hint_for(code: str | None, message: str | None = None) -> str:
    c = (code or "").strip().upper()
    if c in HINTS:
        return HINTS[c]
    msg = (message or "").lower()
    if "totp" in msg or "ab1050" in msg:
        return HINTS["AB1050"]
    if "invalid" in msg and ("pin" in msg or "credential" in msg):
        return HINTS["AB1001"]
    return message or code or "unknown Angel error"
