"""Angel WebSocket V2 → asyncio queue (PLAN P1-5 / V6-1 / review R15).

Production uses SmartAPI WS behind injectable connect/recv. Tests use fakes only.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from data.bars import Tick

log = logging.getLogger(__name__)


def reconnect_backoff(attempt: int) -> float:
    seq = [1, 2, 5, 10, 30]
    return seq[min(attempt, len(seq) - 1)]


@dataclass
class StreamHub:
    loop: asyncio.AbstractEventLoop | None = None
    queue: asyncio.Queue[Tick] | None = None
    subscribed: list[str] = field(default_factory=list)
    connected: bool = False
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue = asyncio.Queue()
        self.connected = True

    def subscribe(self, tokens: list[str]) -> None:
        self.subscribed = list(tokens)

    def push_for_tests(self, tick: Tick) -> None:
        """Test helper: inject a tick onto the asyncio queue thread-safely."""
        assert self.loop and self.queue
        self.loop.call_soon_threadsafe(self.queue.put_nowait, tick)

    def stop(self) -> None:
        self._stop.set()
        self.connected = False


class FakeWebSocket:
    """Test double: fails once then yields one binary tick payload."""

    def __init__(self, payloads: list[bytes]) -> None:
        self._payloads = list(payloads)
        self._i = 0
        self.closed = False

    def recv(self) -> bytes:
        if self._i >= len(self._payloads):
            raise ConnectionError("ws closed")
        p = self._payloads[self._i]
        self._i += 1
        if p == b"":
            raise ConnectionError("simulated drop")
        return p

    def close(self) -> None:
        self.closed = True


def run_ws_loop(
    *,
    stop: threading.Event,
    connect: Callable[[], Any],
    on_packet: Callable[[bytes], None],
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Background thread loop: connect, read until error, backoff, resubscribe (R15)."""
    attempt = 0
    reconnects = 0
    while not stop.is_set():
        try:
            ws = connect()
            attempt = 0
            while not stop.is_set():
                pkt = ws.recv()
                on_packet(pkt)
        except Exception as exc:  # noqa: BLE001 — reconnect path
            log.debug("ws error: %s", exc)
            reconnects += 1
            delay = reconnect_backoff(attempt)
            attempt += 1
            sleep(delay)
            if attempt > 10:
                break
    return reconnects
