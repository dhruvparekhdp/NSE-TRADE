"""WebSocket V2 stub — thread pushes ticks into an asyncio queue (plan P1-5)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from data.bars import Tick


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


def reconnect_backoff(attempt: int) -> float:
    seq = [1, 2, 5, 10, 30]
    return seq[min(attempt, len(seq) - 1)]
