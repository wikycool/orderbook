"""Core types.

Prices and quantities are integers on purpose. Prices are expressed in ticks
(the smallest allowed increment) exactly as real matching engines do it:
floating-point prices make dictionary price levels silently unreliable
(0.1 + 0.2 != 0.3) and introduce rounding drift in fills. Convert to and
from display prices at the edge of the system, never inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass
class Order:
    order_id: int
    side: Side
    price: int          # in ticks
    quantity: int       # original size
    remaining: int      # unfilled size
    active: bool = True

    @property
    def filled(self) -> int:
        return self.quantity - self.remaining


@dataclass(frozen=True)
class Trade:
    maker_id: int       # resting order
    taker_id: int       # aggressing order
    price: int          # execution price (always the maker's price)
    quantity: int
    aggressor: Side     # side of the taker
