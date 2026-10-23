"""R15: WS reconnect/backoff with injectable fake socket."""

from __future__ import annotations

import threading

from data.stream import FakeWebSocket, run_ws_loop


def test_ws_reconnects_after_drop():
    stop = threading.Event()
    attempts = {"n": 0}
    seen: list[bytes] = []

    def connect():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return FakeWebSocket([b""])  # immediate drop
        return FakeWebSocket([b"tick1"])

    def on_packet(pkt: bytes) -> None:
        seen.append(pkt)
        stop.set()

    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    rc = run_ws_loop(stop=stop, connect=connect, on_packet=on_packet, sleep=fake_sleep)
    assert rc >= 1
    assert seen == [b"tick1"]
    assert sleeps[0] == 1.0  # first backoff
