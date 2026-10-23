"""Read-only Angel login check (plan A19.2). Places no orders.

Run on the server or Mac after filling .env — never paste secrets into chat.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import pyotp
        from SmartApi import SmartConnect
    except ImportError:
        print("install smartapi-python pyotp first", file=sys.stderr)
        return 1
    from config.secrets_loader import apply_db_secrets
    from config.settings import get_settings

    try:
        applied = apply_db_secrets()
        print(f"loaded {len(applied)} keys from database")
    except Exception as exc:  # noqa: BLE001
        print(f"db secrets skipped: {exc}")
    s = get_settings()
    if not s.angel_configured:
        print("Angel keys missing (DB /keys or .env)")
        return 1
    api = SmartConnect(api_key=s.angel_api_key.get_secret_value())  # type: ignore[union-attr]
    totp = pyotp.TOTP(s.angel_totp_secret.get_secret_value()).now()  # type: ignore[union-attr]
    sess = api.generateSession(
        s.angel_client_code.get_secret_value(),  # type: ignore[union-attr]
        s.angel_pin.get_secret_value(),  # type: ignore[union-attr]
        totp,
    )
    print("1 LOGIN :", sess.get("status"), sess.get("message"), sess.get("errorcode"))
    if not sess.get("status"):
        return 2
    refresh = (sess.get("data") or {}).get("refreshToken")
    prof = api.getProfile(refresh)
    print("2 PROFILE:", prof.get("status"), "| exchanges:", (prof.get("data") or {}).get("exchanges"))
    funds = api.rmsLimit()
    print("3 FUNDS  :", funds.get("status"), "| available cash:", (funds.get("data") or {}).get("availablecash"))
    q = api.ltpData("NSE", "SBIN-EQ", "3045")
    print("4 LTP    :", q.get("status"), q.get("data"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
