"""Broker protocol placeholders (plan A5). Full types land in P2."""

from __future__ import annotations

from typing import Protocol


class Broker(Protocol):
    """Common surface for AngelBroker and PaperBroker."""

    async def place_order(self, *args, **kwargs): ...  # noqa: ANN002, ANN003
