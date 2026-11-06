"""Keep pytest and CI off the broker and off the public network (plan A15, NSE-001).

SmartAPI's real client logs in with a TOTP. Tests inject fakes instead. This
module is installed from ``tests/conftest.py`` before any test imports the SDK,
so a forgotten fake cannot open a session.
"""

from __future__ import annotations

import socket
import sys
import types
from typing import Any

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_ORIGINAL_SOCKET = socket.socket
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


class OfflineBrokerError(RuntimeError):
    """Raised when test code reaches Angel SmartAPI. No order is sent."""


def host_from_address(address: Any) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def connection_allowed(address: Any) -> bool:
    """Loopback only. aiohttp's TestServer binds there; Angel and NSE do not."""
    host = host_from_address(address)
    return host in _LOOPBACK or host.startswith("127.")


def refuse_offhost(address: Any) -> None:
    if not connection_allowed(address):
        raise OSError(f"offline tests refuse a connection to {host_from_address(address)}")


class GuardedSocket(_ORIGINAL_SOCKET):
    """stdlib socket that rejects anything except loopback."""

    def connect(self, address: Any) -> None:  # type: ignore[override]
        refuse_offhost(address)
        super().connect(address)

    def connect_ex(self, address: Any) -> int:  # type: ignore[override]
        refuse_offhost(address)
        return super().connect_ex(address)


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    refuse_offhost(address)
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def install_socket_guard() -> None:
    if getattr(socket.socket, "_nse_offline_guard", False):
        return
    GuardedSocket._nse_offline_guard = True  # type: ignore[attr-defined]
    socket.socket = GuardedSocket  # type: ignore[misc]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]


class OfflineSmartConnect:
    """Stand-in for ``SmartApi.SmartConnect``. Every method fails closed."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Keep the constructor signature. Do not store or log the api key.
        del args, kwargs

    def generateSession(self, *_args: Any, **_kwargs: Any) -> Any:
        raise OfflineBrokerError("broker login is disabled in tests and CI")

    def __getattr__(self, name: str) -> Any:
        def _blocked(*_args: Any, **_kwargs: Any) -> Any:
            raise OfflineBrokerError(f"SmartConnect.{name} is disabled offline")

        return _blocked


class OfflineSmartWebSocket:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise OfflineBrokerError("SmartWebSocket is disabled offline")


def _ensure_module(name: str) -> types.ModuleType:
    existing = sys.modules.get(name)
    if isinstance(existing, types.ModuleType):
        return existing
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = types.ModuleType(name)
    loaded = sys.modules[name]
    if not isinstance(loaded, types.ModuleType):
        raise TypeError(name)
    return loaded


def install_smartapi_mock() -> None:
    """Replace the SDK classes even when ``smartapi-python`` is installed."""
    package = _ensure_module("SmartApi")
    package.SmartConnect = OfflineSmartConnect  # type: ignore[attr-defined]
    package.SmartWebSocket = OfflineSmartWebSocket  # type: ignore[attr-defined]
    for submodule, attr in (
        ("SmartApi.smartConnect", "SmartConnect"),
        ("SmartApi.smartWebSocketV2", "SmartWebSocketV2"),
        ("SmartApi.smartApiWebsocket", "SmartWebSocket"),
    ):
        try:
            module = _ensure_module(submodule)
        except ImportError:
            continue
        setattr(module, attr, OfflineSmartConnect if attr == "SmartConnect" else OfflineSmartWebSocket)
    # Re-bind after submodule import: SmartApi/__init__.py copies the real class in.
    package.SmartConnect = OfflineSmartConnect  # type: ignore[attr-defined]
    package.SmartWebSocket = OfflineSmartWebSocket  # type: ignore[attr-defined]


def install() -> None:
    install_socket_guard()
    install_smartapi_mock()
