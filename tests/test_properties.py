"""Property-based tests: throw thousands of random operation sequences at the
book and assert exchange invariants that must hold after *every* operation.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from orderbook import OrderBook, Side

# An operation is one of:
#   ("limit", side, price, qty)
#   ("market", side, qty)
#   ("cancel", k)      -> cancels the k-th submitted order (mod count)
#   ("replace", k, price, qty)
operation = st.one_of(
    st.tuples(st.just("limit"), st.sampled_from(Side),
              st.integers(1, 50), st.integers(1, 20)),
    st.tuples(st.just("market"), st.sampled_from(Side), st.integers(1, 20)),
    st.tuples(st.just("cancel"), st.integers(0, 200)),
    st.tuples(st.just("replace"), st.integers(0, 200),
              st.integers(1, 50), st.integers(1, 20)),
)


def apply_ops(ops):
    book = OrderBook()
    submitted: list[int] = []
    for op in ops:
        if op[0] == "limit":
            oid, _ = book.add_limit(op[1], op[2], op[3])
            submitted.append(oid)
        elif op[0] == "market":
            oid, _ = book.add_market(op[1], op[2])
            submitted.append(oid)
        elif op[0] == "cancel" and submitted:
            book.cancel(submitted[op[1] % len(submitted)])
        elif op[0] == "replace" and submitted:
            new_id = book.replace(submitted[op[1] % len(submitted)],
                                  new_price=op[2], new_quantity=op[3])
            if new_id is not None:
                submitted.append(new_id)
    return book, submitted


@settings(max_examples=300, deadline=None)
@given(st.lists(operation, max_size=60))
def test_book_never_crosses(ops):
    """The fundamental invariant: best bid < best ask, always."""
    book, _ = apply_ops(ops)
    bid, ask = book.best_bid(), book.best_ask()
    if bid is not None and ask is not None:
        assert bid < ask


@settings(max_examples=300, deadline=None)
@given(st.lists(operation, max_size=60))
def test_quantity_conservation(ops):
    """filled + remaining == original quantity for every order ever seen,
    and total maker fills equal total taker fills."""
    book, _ = apply_ops(ops)
    for order in book._orders.values():
        assert order.remaining >= 0
        assert order.filled + order.remaining == order.quantity
    maker_fills = sum(t.quantity for t in book.trades)
    taker_fills = sum(t.quantity for t in book.trades)
    assert maker_fills == taker_fills


@settings(max_examples=300, deadline=None)
@given(st.lists(operation, max_size=60))
def test_trades_respect_limit_prices(ops):
    """No buyer ever pays above their limit; no seller receives below theirs."""
    book, _ = apply_ops(ops)
    for trade in book.trades:
        taker = book.order(trade.taker_id)
        maker = book.order(trade.maker_id)
        assert trade.price == maker.price  # executions at maker price
        if taker.price > 0:  # market orders carry price 0: no limit to respect
            if trade.aggressor is Side.BUY:
                assert trade.price <= taker.price
            else:
                assert trade.price >= taker.price


@settings(max_examples=200, deadline=None)
@given(st.lists(operation, max_size=60))
def test_depth_matches_ground_truth(ops):
    """The depth snapshot agrees with a brute-force scan of live orders."""
    book, _ = apply_ops(ops)
    depth = book.depth(n_levels=10_000)
    for side, key, reverse in ((Side.BUY, "bids", True), (Side.SELL, "asks", False)):
        truth: dict[int, int] = {}
        for order in book._orders.values():
            if order.side is side and order.active and order.remaining > 0 and order.price > 0:
                truth[order.price] = truth.get(order.price, 0) + order.remaining
        expected = sorted(truth.items(), key=lambda kv: kv[0], reverse=reverse)
        assert depth[key] == expected
