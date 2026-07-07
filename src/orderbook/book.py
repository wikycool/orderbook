"""Price-time priority limit order book and matching engine.

Data structures:
- One FIFO deque of resting orders per price level (time priority).
- A max-heap of bid prices and a min-heap of ask prices with *lazy deletion*:
  emptied levels stay in the heap until they surface at the top, which keeps
  every operation O(log P) in the number of price levels without the cost of
  rebalancing on every cancel.
- Cancels are lazy too: orders are flagged inactive and skipped/purged when
  they reach the front of their queue, giving O(1) cancel.

Matching semantics (standard exchange rules):
- Executions happen at the *maker's* price: an aggressive order crossing the
  spread gets price improvement.
- Cancel/replace: reducing quantity keeps time priority; changing price or
  increasing quantity forfeits it (the order goes to the back of the new
  level's queue), exactly as on Nasdaq/CME.
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque

from orderbook.types import Order, Side, Trade


class OrderBook:
    def __init__(self) -> None:
        self._levels: dict[Side, dict[int, deque[Order]]] = {
            Side.BUY: {},
            Side.SELL: {},
        }
        # Bid prices are stored negated so heapq's min-heap acts as a max-heap.
        self._heaps: dict[Side, list[int]] = {Side.BUY: [], Side.SELL: []}
        self._orders: dict[int, Order] = {}
        self._id_source = itertools.count(1)
        self.trades: list[Trade] = []

    # ------------------------------------------------------------------ #
    # Top of book
    # ------------------------------------------------------------------ #

    def best_bid(self) -> int | None:
        return self._best_price(Side.BUY)

    def best_ask(self) -> int | None:
        return self._best_price(Side.SELL)

    def spread(self) -> int | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def mid(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def depth(self, n_levels: int = 5) -> dict[str, list[tuple[int, int]]]:
        """Top-of-book snapshot: [(price, total active quantity), ...]."""
        out: dict[str, list[tuple[int, int]]] = {"bids": [], "asks": []}
        for side, key, reverse in ((Side.BUY, "bids", True), (Side.SELL, "asks", False)):
            prices = sorted(self._levels[side], reverse=reverse)
            for price in prices:
                total = sum(o.remaining for o in self._levels[side][price] if o.active)
                if total > 0:
                    out[key].append((price, total))
                if len(out[key]) == n_levels:
                    break
        return out

    def order(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    # ------------------------------------------------------------------ #
    # Order entry
    # ------------------------------------------------------------------ #

    def add_limit(self, side: Side, price: int, quantity: int) -> tuple[int, list[Trade]]:
        """Submit a limit order. Returns (order_id, trades executed on entry).

        Any unfilled remainder rests on the book.
        """
        self._validate(price=price, quantity=quantity)
        order = Order(next(self._id_source), side, price, quantity, quantity)
        self._orders[order.order_id] = order

        trades = self._match(order, limit_price=price)
        if order.remaining > 0:
            self._rest(order)
        return order.order_id, trades

    def add_market(self, side: Side, quantity: int) -> tuple[int, list[Trade]]:
        """Submit a market order. Returns (order_id, trades).

        The unfilled remainder (if liquidity runs out) is cancelled, never
        rested: a market order has no price to rest at.
        """
        self._validate(quantity=quantity)
        order = Order(next(self._id_source), side, 0, quantity, quantity, active=False)
        self._orders[order.order_id] = order
        trades = self._match(order, limit_price=None)
        order.remaining = order.remaining  # remainder is simply dropped
        return order.order_id, trades

    def cancel(self, order_id: int) -> bool:
        """Cancel a resting order. O(1). Returns False if unknown or done."""
        order = self._orders.get(order_id)
        if order is None or not order.active or order.remaining == 0:
            return False
        order.active = False
        return True

    def replace(self, order_id: int, *, new_price: int | None = None,
                new_quantity: int | None = None) -> int | None:
        """Cancel/replace. Returns the surviving order id, or None on failure.

        Quantity reduction at the same price keeps time priority (modify in
        place). A price change or a quantity increase forfeits priority: the
        original is cancelled and a fresh order enters the book.
        """
        order = self._orders.get(order_id)
        if order is None or not order.active or order.remaining == 0:
            return None
        price = new_price if new_price is not None else order.price
        quantity = new_quantity if new_quantity is not None else order.remaining
        self._validate(price=price, quantity=quantity)

        if price == order.price and quantity <= order.remaining:
            order.remaining = quantity
            return order.order_id

        self.cancel(order_id)
        new_id, _ = self.add_limit(order.side, price, quantity)
        return new_id

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _match(self, taker: Order, limit_price: int | None) -> list[Trade]:
        trades: list[Trade] = []
        book_side = taker.side.opposite
        while taker.remaining > 0:
            best = self._best_price(book_side)
            if best is None:
                break
            if limit_price is not None:
                if taker.side is Side.BUY and best > limit_price:
                    break
                if taker.side is Side.SELL and best < limit_price:
                    break
            queue = self._levels[book_side][best]
            maker = queue[0]
            if not maker.active or maker.remaining == 0:
                queue.popleft()
                self._gc_level(book_side, best)
                continue
            fill = min(taker.remaining, maker.remaining)
            maker.remaining -= fill
            taker.remaining -= fill
            trade = Trade(maker.order_id, taker.order_id, best, fill, taker.side)
            trades.append(trade)
            self.trades.append(trade)
            if maker.remaining == 0:
                maker.active = False
                queue.popleft()
                self._gc_level(book_side, best)
        return trades

    def _rest(self, order: Order) -> None:
        levels = self._levels[order.side]
        if order.price not in levels:
            levels[order.price] = deque()
            key = -order.price if order.side is Side.BUY else order.price
            heapq.heappush(self._heaps[order.side], key)
        levels[order.price].append(order)

    def _best_price(self, side: Side) -> int | None:
        heap = self._heaps[side]
        levels = self._levels[side]
        while heap:
            price = -heap[0] if side is Side.BUY else heap[0]
            queue = levels.get(price)
            if queue is None:
                heapq.heappop(heap)  # level was emptied earlier: lazy delete
                continue
            # Purge dead orders sitting at the front of the queue.
            while queue and (not queue[0].active or queue[0].remaining == 0):
                queue.popleft()
            if not queue:
                del levels[price]
                heapq.heappop(heap)
                continue
            return price
        return None

    def _gc_level(self, side: Side, price: int) -> None:
        queue = self._levels[side].get(price)
        if queue is not None and not queue:
            del self._levels[side][price]

    @staticmethod
    def _validate(price: int | None = None, quantity: int | None = None) -> None:
        if price is not None and (not isinstance(price, int) or price <= 0):
            raise ValueError(f"price must be a positive integer tick, got {price!r}")
        if quantity is not None and (not isinstance(quantity, int) or quantity <= 0):
            raise ValueError(f"quantity must be a positive integer, got {quantity!r}")
