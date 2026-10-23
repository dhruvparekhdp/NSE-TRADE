"""Build Angel SmartConnect with real ClientPublicIP / LocalIP / MAC (PLAN_V2 V0-7)."""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any

from config.settings import get_settings

log = logging.getLogger(__name__)


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def mac_address() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> ele) & 0xFF:02x}" for ele in range(40, -1, -8))


def public_ip_for_headers() -> str:
    """Prefer expected_static_ip (registered with Angel); else leave empty for SDK."""
    settings = get_settings()
    return (settings.expected_static_ip or "").strip()


def apply_ip_headers(api: Any) -> dict[str, str]:
    """Stamp the three headers Angel expects; return what we set (for tests)."""
    headers = {
        "X-ClientPublicIP": public_ip_for_headers() or "127.0.0.1",
        "X-ClientLocalIP": local_ip(),
        "X-MACAddress": mac_address(),
    }
    # smartapi-python keeps a requests session on several attribute names across versions
    for attr in ("_session", "session", "reqsession"):
        sess = getattr(api, attr, None)
        if sess is not None and hasattr(sess, "headers"):
            sess.headers.update(headers)
            break
    for key, val in headers.items():
        try:
            setattr(api, key.replace("-", "_").lower(), val)
        except Exception:  # noqa: BLE001
            pass
    # Common SmartConnect fields (1.4/1.5)
    for attr, key in (
        ("clientPublicIp", "X-ClientPublicIP"),
        ("clientLocalIp", "X-ClientLocalIP"),
        ("clientMacAddress", "X-MACAddress"),
        ("public_ip", "X-ClientPublicIP"),
        ("local_ip", "X-ClientLocalIP"),
        ("macAddress", "X-MACAddress"),
    ):
        if hasattr(api, attr) or True:
            try:
                setattr(api, attr, headers[key])
            except Exception:  # noqa: BLE001
                pass
    log.info(
        "angel headers public=%s local=%s mac=…%s",
        headers["X-ClientPublicIP"],
        headers["X-ClientLocalIP"],
        headers["X-MACAddress"][-5:],
    )
    return headers


def build_smart_connect() -> Any:
    from SmartApi import SmartConnect

    settings = get_settings()
    key = settings.angel_api_key.get_secret_value() if settings.angel_api_key else ""
    api = SmartConnect(key)
    apply_ip_headers(api)
    return api
