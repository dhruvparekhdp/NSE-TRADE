"""Single choke point for Angel place, modify, and cancel (plan A8 / A15).

Live sends stay impossible unless both confirmation env vars are on and the
existing mode=live / live_orders gate is on. Paper, shadow, and pytest never
satisfy that. SmartAPI order methods are called only from this module, and
only after assert_live_orders_allowed().
"""

from __future__ import annotations

from typing import Any

from broker.errors import Rejected
from config.settings import get_settings

# Second switch is LIVE_ORDERS_CONFIRM. Both default off (unset).
ENV_ENABLED = "LIVE_ORDERS_ENABLED"
ENV_CONFIRM = "LIVE_ORDERS_CONFIRM"
ORDER_METHODS = ("placeOrder", "modifyOrder", "cancelOrder")


def flags_allow_live(*, enabled: bool, confirmed: bool, mode: str, live_orders: bool) -> bool:
    """Pure rule: both new env flags, plus the plan A15 dual gate."""
    return bool(enabled) and bool(confirmed) and mode == "live" and bool(live_orders)


def live_orders_allowed() -> bool:
    """Read the process settings. False unless every flag is on."""
    settings = get_settings()
    return flags_allow_live(
        enabled=bool(getattr(settings, "live_orders_enabled", False)),
        confirmed=bool(getattr(settings, "live_orders_confirm", False)),
        mode=str(settings.mode),
        live_orders=bool(settings.live_orders),
    )


def assert_live_orders_allowed() -> None:
    """Raise before any SmartAPI order method. Call this first on every path."""
    if not live_orders_allowed():
        raise Rejected(
            "live orders disabled (need LIVE_ORDERS_ENABLED=true and LIVE_ORDERS_CONFIRM=true,"
            " plus mode=live and live_orders=true)"
        )


def startup_banner(settings: Any | None = None) -> str:
    """One line for process start: mode, and live OFF unless the guard would pass."""
    settings = settings if settings is not None else get_settings()
    live = "ON" if live_orders_allowed() else "OFF"
    return f"nse-engine mode={settings.mode} live={live} listening on http://{settings.web_host}:{settings.web_port}"


def place_order(api: Any, params: dict[str, Any]) -> Any:
    """SmartAPI placeOrder. Guard runs before the SDK call."""
    assert_live_orders_allowed()
    return api.placeOrder(params)


def modify_order(api: Any, params: dict[str, Any]) -> Any:
    """SmartAPI modifyOrder. Guard runs before the SDK call."""
    assert_live_orders_allowed()
    return api.modifyOrder(params)


def cancel_order(api: Any, order_id: str, variety: str = "NORMAL") -> Any:
    """SmartAPI cancelOrder. Guard runs before the SDK call."""
    assert_live_orders_allowed()
    return api.cancelOrder(order_id, variety)
