"""PaperBroker — same fill rules as plan A9.5; costs from core.costs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.costs import CostRates, rates_for, round_trip

OrderType = Literal["LIMIT", "STOPLOSS_LIMIT"]
SideStr = Literal["BUY", "SELL"]
Product = Literal["INTRADAY", "DELIVERY"]
Status = Literal["NEW", "SUBMITTED", "OPEN", "PARTIAL", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"]


@dataclass
class PaperOrder:
    client_tag: str
    symbol: str
    side: SideStr
    qty: int
    order_type: OrderType
    product: Product
    purpose: str
    price: float | None
    trigger: float | None
    status: Status = "OPEN"
    filled_qty: int = 0
    avg_price: float | None = None
    broker_order_id: str = ""


@dataclass
class PaperPosition:
    symbol: str
    product: Product
    qty: int
    avg_price: float
    side: int  # +1 long / -1 short


@dataclass
class PaperBroker:
    capital: float
    slippage_pct_mis: float = 0.03
    slippage_pct_cnc: float = 0.05
    mis_margin_pct: float = 20.0
    session_open: bool = True
    orders: dict[str, PaperOrder] = field(default_factory=dict)
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    cash: float = 0.0
    _seq: int = 0
    last_ltp: dict[str, float] = field(default_factory=dict)
    last_ask: dict[str, float] = field(default_factory=dict)
    last_bid: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cash == 0.0:
            self.cash = self.capital

    def _slip(self, product: Product) -> float:
        return self.slippage_pct_mis if product == "INTRADAY" else self.slippage_pct_cnc

    def on_tick(
        self, symbol: str, ltp: float, bid: float | None = None, ask: float | None = None
    ) -> list[dict[str, Any]]:
        self.last_ltp[symbol] = ltp
        if bid is not None:
            self.last_bid[symbol] = bid
        if ask is not None:
            self.last_ask[symbol] = ask
        fills: list[dict[str, Any]] = []
        for order in list(self.orders.values()):
            if order.symbol != symbol or order.status not in {"OPEN", "SUBMITTED", "PARTIAL"}:
                continue
            fill = self._try_fill(order, ltp, bid, ask)
            if fill:
                fills.append(fill)
        return fills

    def _try_fill(
        self,
        order: PaperOrder,
        ltp: float,
        bid: float | None,
        ask: float | None,
    ) -> dict[str, Any] | None:
        slip = self._slip(order.product) / 100.0
        px: float | None = None
        if order.order_type == "LIMIT":
            assert order.price is not None
            if order.side == "BUY":
                ref = ask if ask is not None else ltp
                if ref <= order.price:
                    px = min(order.price, ref) * (1.0 + slip)
            else:
                ref = bid if bid is not None else ltp
                if ref >= order.price:
                    px = max(order.price, ref) * (1.0 - slip)
        elif order.order_type == "STOPLOSS_LIMIT":
            assert order.trigger is not None and order.price is not None
            if order.side == "SELL":
                if ltp <= order.trigger:
                    # fill at worse of LTP/trigger minus slippage; if gaps through limit, stay open
                    raw = min(ltp, order.trigger) * (1.0 - slip - 0.0005)
                    if raw < order.price:
                        return None  # gap through — watchdog handles
                    px = raw
            else:  # buy stop
                if ltp >= order.trigger:
                    raw = max(ltp, order.trigger) * (1.0 + slip + 0.0005)
                    if raw > order.price:
                        return None
                    px = raw
        if px is None:
            return None
        order.status = "FILLED"
        order.filled_qty = order.qty
        order.avg_price = round(px, 2)
        self._apply_fill(order)
        return {
            "client_tag": order.client_tag,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "price": order.avg_price,
            "product": order.product,
            "purpose": order.purpose,
        }

    def _apply_fill(self, order: PaperOrder) -> None:
        """Update positions and cash. MIS closes release margin + realised P&L − costs (B7)."""
        signed = order.qty if order.side == "BUY" else -order.qty
        key = f"{order.symbol}:{order.product}"
        pos = self.positions.get(key)
        px = order.avg_price or 0.0
        notional = order.qty * px

        # CNC: no short entry; buy needs cash
        if order.product == "DELIVERY" and order.purpose == "entry" and order.side == "SELL":
            order.status = "REJECTED"
            order.filled_qty = 0
            order.avg_price = None
            return
        if order.product == "DELIVERY" and order.side == "BUY" and order.purpose == "entry":
            est_cost = self.round_trip_costs(notional, notional, "DELIVERY") * 0.5
            if notional + est_cost > self.cash:
                order.status = "REJECTED"
                order.filled_qty = 0
                order.avg_price = None
                return

        if order.product == "INTRADAY" and order.purpose == "entry" and pos is None:
            margin = notional * self.mis_margin_pct / 100.0
            if margin > self.cash:
                order.status = "REJECTED"
                order.filled_qty = 0
                order.avg_price = None
                return

        if pos is None:
            self.positions[key] = PaperPosition(
                symbol=order.symbol,
                product=order.product,
                qty=signed,
                avg_price=px,
                side=1 if signed > 0 else -1,
            )
            if order.purpose == "entry":
                if order.product == "DELIVERY":
                    self.cash -= notional
                else:
                    self.cash -= notional * self.mis_margin_pct / 100.0
            return

        new_qty = pos.qty + signed
        if new_qty == 0:
            # flat: realise P&L
            if pos.side > 0:
                pnl = (px - pos.avg_price) * abs(pos.qty)
                buy_v, sell_v = pos.avg_price * abs(pos.qty), px * abs(pos.qty)
            else:
                pnl = (pos.avg_price - px) * abs(pos.qty)
                buy_v, sell_v = px * abs(pos.qty), pos.avg_price * abs(pos.qty)
            costs = self.round_trip_costs(buy_v, sell_v, order.product)
            if order.product == "DELIVERY":
                self.cash += notional - costs
            else:
                margin = abs(pos.qty) * pos.avg_price * self.mis_margin_pct / 100.0
                self.cash += margin + pnl - costs
            del self.positions[key]
        else:
            pos.qty = new_qty
            pos.side = 1 if new_qty > 0 else -1

    def place_order(self, **kwargs: Any) -> PaperOrder:
        if not self.session_open and kwargs.get("purpose") == "entry":
            order = PaperOrder(
                client_tag=kwargs["client_tag"],
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                qty=int(kwargs["qty"]),
                order_type=kwargs["order_type"],
                product=kwargs["product"],
                purpose=kwargs.get("purpose", "entry"),
                price=kwargs.get("price"),
                trigger=kwargs.get("trigger"),
                status="REJECTED",
            )
            self.orders[order.client_tag] = order
            return order
        # idempotent by tag
        existing = self.orders.get(kwargs["client_tag"])
        if existing is not None:
            return existing
        self._seq += 1
        order = PaperOrder(
            client_tag=kwargs["client_tag"],
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            qty=int(kwargs["qty"]),
            order_type=kwargs["order_type"],
            product=kwargs["product"],
            purpose=kwargs.get("purpose", "entry"),
            price=kwargs.get("price"),
            trigger=kwargs.get("trigger"),
            status="OPEN",
            broker_order_id=f"P{self._seq}",
        )
        self.orders[order.client_tag] = order
        return order

    def cancel_order(self, client_tag: str) -> bool:
        o = self.orders.get(client_tag)
        if o and o.status in {"OPEN", "SUBMITTED", "PARTIAL"}:
            o.status = "CANCELLED"
            return True
        return False

    def round_trip_costs(self, buy_value: float, sell_value: float, product: Product) -> float:
        prod: Any = "MIS" if product == "INTRADAY" else "CNC"
        rates: CostRates = rates_for(prod)
        return round_trip(buy_value, sell_value, prod, rates).total
