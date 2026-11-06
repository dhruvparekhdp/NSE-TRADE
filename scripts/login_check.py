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
    from config.broker_secrets import BrokerSecretsMissing, load_broker_secrets
    from config.secrets_loader import apply_db_secrets

    try:
        applied = apply_db_secrets()
        print(f"loaded {len(applied)} keys from database")
    except Exception as exc:  # noqa: BLE001
        print(f"db secrets skipped: {exc}")
    try:
        secrets = load_broker_secrets()
    except BrokerSecretsMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    api = SmartConnect(api_key=secrets.api_key)
    totp = pyotp.TOTP(secrets.totp_secret).now()
    sess = api.generateSession(secrets.client_code, secrets.pin, totp)
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
