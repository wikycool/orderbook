import pytest

from orderbook import OrderBook, Side


@pytest.fixture
def book():
    return OrderBook()


def test_resting_order_appears_at_top(book):
    book.add_limit(Side.BUY, 100, 10)
    book.add_limit(Side.SELL, 102, 5)
    assert book.best_bid() == 100
    assert book.best_ask() == 102
    assert book.spread() == 2
    assert book.mid() == 101.0


def test_crossing_limit_executes_at_maker_price(book):
    maker_id, _ = book.add_limit(Side.SELL, 101, 10)
    taker_id, trades = book.add_limit(Side.BUY, 105, 10)  # willing to pay 105
    assert len(trades) == 1
    t = trades[0]
    assert t.price == 101              # price improvement for the taker
    assert t.maker_id == maker_id
    assert t.taker_id == taker_id
    assert t.aggressor is Side.BUY
    assert book.best_ask() is None
    assert book.best_bid() is None     # fully filled, nothing rests


def test_partial_fill_rests_remainder(book):
    book.add_limit(Side.SELL, 101, 4)
    _, trades = book.add_limit(Side.BUY, 101, 10)
    assert sum(t.quantity for t in trades) == 4
    assert book.best_bid() == 101      # remaining 6 rests as a bid
    depth = book.depth()
    assert depth["bids"] == [(101, 6)]


def test_time_priority_within_level(book):
    first, _ = book.add_limit(Side.SELL, 101, 5)
    second, _ = book.add_limit(Side.SELL, 101, 5)
    _, trades = book.add_limit(Side.BUY, 101, 5)
    assert trades[0].maker_id == first
    _, trades = book.add_limit(Side.BUY, 101, 5)
    assert trades[0].maker_id == second


def test_price_priority_across_levels(book):
    book.add_limit(Side.SELL, 103, 5)
    cheap, _ = book.add_limit(Side.SELL, 101, 5)
    _, trades = book.add_limit(Side.BUY, 103, 5)
    assert trades[0].maker_id == cheap
    assert trades[0].price == 101


def test_market_order_sweeps_levels(book):
    book.add_limit(Side.SELL, 101, 3)
    book.add_limit(Side.SELL, 102, 3)
    book.add_limit(Side.SELL, 103, 3)
    _, trades = book.add_market(Side.BUY, 8)
    assert [(t.price, t.quantity) for t in trades] == [(101, 3), (102, 3), (103, 2)]
    assert book.best_ask() == 103
    assert book.depth()["asks"] == [(103, 1)]


def test_market_order_remainder_is_cancelled_not_rested(book):
    book.add_limit(Side.SELL, 101, 3)
    _, trades = book.add_market(Side.BUY, 10)
    assert sum(t.quantity for t in trades) == 3
    assert book.best_bid() is None     # nothing rested


def test_cancel_removes_liquidity(book):
    oid, _ = book.add_limit(Side.BUY, 100, 10)
    assert book.cancel(oid) is True
    assert book.best_bid() is None
    assert book.cancel(oid) is False   # already cancelled
    assert book.cancel(999) is False   # unknown


def test_cancelled_order_never_trades(book):
    oid, _ = book.add_limit(Side.SELL, 101, 10)
    book.cancel(oid)
    _, trades = book.add_limit(Side.BUY, 105, 5)
    assert trades == []
    assert book.best_bid() == 105      # aggressor rests instead


def test_replace_quantity_reduction_keeps_priority(book):
    first, _ = book.add_limit(Side.SELL, 101, 10)
    book.add_limit(Side.SELL, 101, 10)
    surviving = book.replace(first, new_quantity=5)
    assert surviving == first          # same id: priority kept
    _, trades = book.add_limit(Side.BUY, 101, 5)
    assert trades[0].maker_id == first


def test_replace_price_change_loses_priority(book):
    first, _ = book.add_limit(Side.SELL, 102, 10)
    second, _ = book.add_limit(Side.SELL, 101, 10)
    moved = book.replace(first, new_price=101)
    assert moved != first
    _, trades = book.add_limit(Side.BUY, 101, 10)
    assert trades[0].maker_id == second  # original 101 order fills first


def test_replace_can_trigger_immediate_execution(book):
    book.add_limit(Side.SELL, 105, 5)
    oid, _ = book.add_limit(Side.BUY, 100, 5)
    book.replace(oid, new_price=105)   # repriced through the spread
    assert book.best_ask() is None
    assert book.best_bid() is None


def test_validation_rejects_garbage(book):
    with pytest.raises(ValueError):
        book.add_limit(Side.BUY, 0, 10)
    with pytest.raises(ValueError):
        book.add_limit(Side.BUY, 100, -1)
    with pytest.raises(ValueError):
        book.add_market(Side.SELL, 0)
