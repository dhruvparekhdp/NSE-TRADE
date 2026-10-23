"""Order manager state machine + bracket emulation (plan A9.4). Works against Broker protocol."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from core.ticks import round_buy_limit, round_sell_limit, round_stop_trigger, tick_for_price

Status = Literal["NEW", "SUBMITTED", "OPEN", "PARTIAL", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"]


def make_client_tag(trade_date: str, book: str, strategy_code: str, seq: int) -> str:
    """ne{yyMMdd}{book}{strategy 2 chars}{seq 4 digits} — plan A9.4."""
    yymmdd = trade_date.replace("-", "")[2:]
    return f"ne{yymmdd}{book}{strategy_code[:2].upper()}{seq:04d}"


@dataclass
class ManagedOrder:
    client_tag: str
    symbol: str
    side: str
    qty: int
    order_type: str
    product: str
    purpose: str
    price: float | None
    trigger: float | None
    status: Status = "NEW"
    broker_order_id: str | None = None
    filled_qty: int = 0
    avg_price: float | None = None
    placed_ms: int = 0


@dataclass
class Bracket:
    trade_id: int
    symbol: str
    entry: ManagedOrder
    stop: ManagedOrder | None = None
    target: ManagedOrder | None = None
    entry_timeout_s: int = 20
    stop_trigger: float | None = None
    stop_limit: float | None = None
    target_price: float | None = None
    qty: int = 0
    side: int = 1


@dataclass
class OrderManager:
    broker: Any
    entry_timeout_s: int = 20
    stop_limit_buffer_pct: float = 0.5
    stop_watchdog_s: int = 10
    entry_limit_offset_pct: float = 0.05
    brackets: dict[int, Bracket] = field(default_factory=dict)
    orders_by_tag: dict[str, ManagedOrder] = field(default_factory=dict)
    _seq: int = 0
    reconcile_faults: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)

    def next_tag(self, trade_date: str, book: str, strategy_code: str) -> str:
        self._seq += 1
        return make_client_tag(trade_date, book, strategy_code, self._seq)

    def submit_bracket(
        self,
        *,
        trade_id: int,
        trade_date: str,
        strategy_code: str,
        symbol: str,
        side: int,
        qty: int,
        book: str,
        entry_ref: float,
        stop: float,
        target: float | None,
        ask: float | None = None,
        bid: float | None = None,
        now_ms: int | None = None,
        tick: float | None = None,
    ) -> Bracket:
        if symbol in self.reconcile_faults:
            raise RuntimeError(f"reconcile unresolved for {symbol}")
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        product = "INTRADAY" if book == "A" else "DELIVERY"
        side_str = "BUY" if side > 0 else "SELL"
        if side > 0:
            ref = ask if ask is not None else entry_ref
            raw = ref * (1 + self.entry_limit_offset_pct / 100.0)
            t = tick if tick is not None else tick_for_price(ref)
            limit = round_buy_limit(raw, t)
        else:
            ref = bid if bid is not None else entry_ref
            raw = ref * (1 - self.entry_limit_offset_pct / 100.0)
            t = tick if tick is not None else tick_for_price(ref)
            limit = round_sell_limit(raw, t)
        stop_trig = round_stop_trigger(stop, side=side, tick=t)
        tgt = None if target is None else (
            round_sell_limit(target, t) if side > 0 else round_buy_limit(target, t)
        )
        tag = self.next_tag(trade_date, book, strategy_code)
        # idempotent: if tag already at broker, reuse
        existing = self.orders_by_tag.get(tag)
        if existing:
            return self.brackets[trade_id]
        entry = ManagedOrder(
            client_tag=tag,
            symbol=symbol,
            side=side_str,
            qty=qty,
            order_type="LIMIT",
            product=product,
            purpose="entry",
            price=limit,
            trigger=None,
            status="SUBMITTED",
            placed_ms=now,
        )
        self.broker.place_order(
            client_tag=tag,
            symbol=symbol,
            side=side_str,
            qty=qty,
            order_type="LIMIT",
            product=product,
            purpose="entry",
            price=limit,
            trigger=None,
        )
        entry.status = "OPEN"
        self.orders_by_tag[tag] = entry
        br = Bracket(
            trade_id=trade_id,
            symbol=symbol,
            entry=entry,
            entry_timeout_s=self.entry_timeout_s,
            stop_trigger=stop_trig,
            qty=qty,
            side=side,
            target_price=tgt,
        )
        # precompute stop limit (away from market vs trigger); always on-tick
        buf = self.stop_limit_buffer_pct / 100.0
        if side > 0:
            br.stop_limit = round_sell_limit(stop_trig * (1 - buf), t)
        else:
            br.stop_limit = round_buy_limit(stop_trig * (1 + buf), t)
        self.brackets[trade_id] = br
        self.events.append({"kind": "entry_submitted", "tag": tag, "symbol": symbol})
        return br

    def on_fill(self, fill: dict[str, Any], now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        tag = fill["client_tag"]
        order = self.orders_by_tag.get(tag)
        if not order:
            return
        order.status = "FILLED"
        order.filled_qty = fill["qty"]
        order.avg_price = fill["price"]
        # find bracket
        for br in self.brackets.values():
            if br.entry.client_tag == tag and br.stop is None:
                self._place_exits(br, now)
            elif br.target and br.target.client_tag == tag:
                if br.stop:
                    self.broker.cancel_order(br.stop.client_tag)
                    br.stop.status = "CANCELLED"
            elif br.stop and br.stop.client_tag == tag:
                if br.target:
                    self.broker.cancel_order(br.target.client_tag)
                    br.target.status = "CANCELLED"

    def _place_exits(self, br: Bracket, now_ms: int) -> None:
        product = br.entry.product
        stop_side = "SELL" if br.side > 0 else "BUY"
        stop_tag = br.entry.client_tag + "S"
        stop = ManagedOrder(
            client_tag=stop_tag,
            symbol=br.symbol,
            side=stop_side,
            qty=br.qty,
            order_type="STOPLOSS_LIMIT",
            product=product,
            purpose="stop",
            price=br.stop_limit,
            trigger=br.stop_trigger,
            status="SUBMITTED",
            placed_ms=now_ms,
        )
        self.broker.place_order(
            client_tag=stop_tag,
            symbol=br.symbol,
            side=stop_side,
            qty=br.qty,
            order_type="STOPLOSS_LIMIT",
            product=product,
            purpose="stop",
            price=br.stop_limit,
            trigger=br.stop_trigger,
        )
        stop.status = "OPEN"
        br.stop = stop
        self.orders_by_tag[stop_tag] = stop
        if br.target_price is not None:
            tgt_tag = br.entry.client_tag + "T"
            tgt = ManagedOrder(
                client_tag=tgt_tag,
                symbol=br.symbol,
                side=stop_side,
                qty=br.qty,
                order_type="LIMIT",
                product=product,
                purpose="target",
                price=br.target_price,
                trigger=None,
                status="SUBMITTED",
                placed_ms=now_ms,
            )
            self.broker.place_order(
                client_tag=tgt_tag,
                symbol=br.symbol,
                side=stop_side,
                qty=br.qty,
                order_type="LIMIT",
                product=product,
                purpose="target",
                price=br.target_price,
                trigger=None,
            )
            tgt.status = "OPEN"
            br.target = tgt
            self.orders_by_tag[tgt_tag] = tgt

    def tick_watchdog(self, symbol: str, ltp: float, now_ms: int) -> None:
        for br in self.brackets.values():
            if br.symbol != symbol or not br.stop or br.stop.status != "OPEN":
                continue
            assert br.stop_trigger is not None
            crossed = (br.side > 0 and ltp <= br.stop_trigger) or (br.side < 0 and ltp >= br.stop_trigger)
            if not crossed:
                continue
            # if still open longer than watchdog after cross, force exit
            age_s = (now_ms - br.stop.placed_ms) / 1000.0
            if age_s < self.stop_watchdog_s:
                continue
            self.broker.cancel_order(br.stop.client_tag)
            br.stop.status = "CANCELLED"
            exit_side = br.stop.side
            through = ltp * (0.995 if exit_side == "SELL" else 1.005)
            t = tick_for_price(ltp)
            px = round_sell_limit(through, t) if exit_side == "SELL" else round_buy_limit(through, t)
            tag = br.entry.client_tag + "W"
            self.broker.place_order(
                client_tag=tag,
                symbol=symbol,
                side=exit_side,
                qty=br.qty,
                order_type="LIMIT",
                product=br.entry.product,
                purpose="exit",
                price=px,
                trigger=None,
            )

    def cancel_unfilled_entries(self, now_ms: int) -> None:
        for br in self.brackets.values():
            if br.entry.status != "OPEN":
                continue
            if (now_ms - br.entry.placed_ms) / 1000.0 >= br.entry_timeout_s:
                self.broker.cancel_order(br.entry.client_tag)
                br.entry.status = "CANCELLED"
                self.events.append({"kind": "entry_timeout", "tag": br.entry.client_tag})

    def square_off(self, symbol: str | None = None) -> None:
        for br in list(self.brackets.values()):
            if symbol and br.symbol != symbol:
                continue
            for leg in (br.stop, br.target):
                if leg and leg.status == "OPEN":
                    self.broker.cancel_order(leg.client_tag)
                    leg.status = "CANCELLED"
            # protected limit exit left to caller/broker tick

    def mark_reconcile_fault(self, symbol: str, on: bool = True) -> None:
        if on:
            self.reconcile_faults.add(symbol)
        else:
            self.reconcile_faults.discard(symbol)
