"""Microstructure analytics over the book and the trade tape."""

from __future__ import annotations

from orderbook.book import OrderBook
from orderbook.types import Side, Trade


def vwap(trades: list[Trade]) -> float | None:
    """Volume-weighted average execution price, in ticks."""
    volume = sum(t.quantity for t in trades)
    if volume == 0:
        return None
    return sum(t.price * t.quantity for t in trades) / volume


def signed_volume(trades: list[Trade]) -> int:
    """Net aggressor volume: buys positive, sells negative.

    A standard proxy for order-flow imbalance from the tape alone.
    """
    return sum(
        t.quantity if t.aggressor is Side.BUY else -t.quantity for t in trades
    )


def book_imbalance(book: OrderBook, n_levels: int = 1) -> float | None:
    """(bid_qty - ask_qty) / (bid_qty + ask_qty) over the top n levels.

    Ranges from -1 (all asks) to +1 (all bids); a common short-horizon
    price-pressure signal.
    """
    depth = book.depth(n_levels)
    bid_qty = sum(q for _, q in depth["bids"])
    ask_qty = sum(q for _, q in depth["asks"])
    total = bid_qty + ask_qty
    if total == 0:
        return None
    return (bid_qty - ask_qty) / total


def effective_spread(trade: Trade, mid_at_entry: float) -> float:
    """2 * |execution price - mid|: what the taker actually paid to cross."""
    return 2.0 * abs(trade.price - mid_at_entry)
