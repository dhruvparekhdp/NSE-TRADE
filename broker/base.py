"""Sync Broker protocol (PLAN_V2 V4-5 / B11; review R8). Paper + Angel implement this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

SideStr = Literal["BUY", "SELL"]
OrderType = Literal["LIMIT", "STOPLOSS_LIMIT"]
Product = Literal["INTRADAY", "DELIVERY"]


@dataclass(frozen=True)
class OrderRequest:
    client_tag: str
    symbol: str
    side: SideStr
    qty: int
    order_type: OrderType
    product: Product
    purpose: str
    price: float | None
    trigger: float | None


@dataclass
class OrderAck:
    client_tag: str
    broker_order_id: str | None = None
    status: str = "OPEN"
    raw: dict[str, Any] | None = None


class Broker(Protocol):
    """Common sync surface for PaperBroker and AngelBroker. No async."""

    def place_order(
        self,
        *,
        client_tag: str,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        product: str,
        purpose: str,
        price: float | None,
        trigger: float | None,
    ) -> Any: ...

    def cancel_order(self, client_tag: str) -> Any: ...

    def get_order_by_tag(self, client_tag: str) -> Any | None: ...
