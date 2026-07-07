from orderbook import OrderBook, Side, book_imbalance, signed_volume, vwap
from orderbook.types import Trade


def make_trade(price, qty, aggressor):
    return Trade(maker_id=1, taker_id=2, price=price, quantity=qty,
                 aggressor=aggressor)


def test_vwap():
    trades = [make_trade(100, 10, Side.BUY), make_trade(102, 30, Side.BUY)]
    assert vwap(trades) == (100 * 10 + 102 * 30) / 40
    assert vwap([]) is None


def test_signed_volume():
    trades = [make_trade(100, 10, Side.BUY), make_trade(100, 4, Side.SELL)]
    assert signed_volume(trades) == 6


def test_book_imbalance():
    book = OrderBook()
    book.add_limit(Side.BUY, 99, 30)
    book.add_limit(Side.SELL, 101, 10)
    assert book_imbalance(book) == (30 - 10) / 40
    assert book_imbalance(OrderBook()) is None
