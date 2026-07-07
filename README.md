# orderbook

A price-time priority limit order book and matching engine, built for market-microstructure experiments — and verified with **property-based testing**: thousands of random operation sequences are thrown at the book, and exchange invariants must survive every one of them.

## Why this exists

Everyone's first order book is a sorted list with O(n) inserts and floating-point prices. This one is built the way real matching engines are:

- **Integer tick prices.** Floating-point prices make hash-based price levels silently unreliable (`0.1 + 0.2 != 0.3`). Prices here are integers in ticks; conversion to display prices happens at the edge of the system, never inside it.
- **O(log P) top-of-book, O(1) cancel.** Bid/ask price heaps with *lazy deletion* (emptied levels purge when they surface), FIFO deques per level for time priority, and tombstone-flag cancels.
- **Real exchange semantics.** Executions at the maker's price (aggressors get price improvement). Cancel/replace follows Nasdaq/CME rules: reducing quantity keeps time priority, repricing or upsizing forfeits it.

## Quick start

```bash
pip install -e ".[dev]"
pytest
```

```python
from orderbook import OrderBook, Side

book = OrderBook()
book.add_limit(Side.SELL, price=101, quantity=10)
book.add_limit(Side.SELL, price=102, quantity=20)

order_id, trades = book.add_limit(Side.BUY, price=105, quantity=15)
# trades: 10 @ 101, then 5 @ 102 — filled at maker prices, not 105

book.best_ask()   # 102
book.depth(5)     # {'bids': [], 'asks': [(102, 15)]}
```

## Microstructure analytics

The tape and the book are first-class research objects:

```python
from orderbook import vwap, signed_volume, book_imbalance

vwap(book.trades)          # volume-weighted average execution price
signed_volume(book.trades) # net aggressor flow (order-flow imbalance proxy)
book_imbalance(book, 3)    # (bid - ask) / (bid + ask) qty over top 3 levels
```

## Property-based testing

Unit tests check known scenarios; the interesting bugs live in sequences nobody thought to write down. `tests/test_properties.py` uses [Hypothesis](https://hypothesis.readthedocs.io/) to generate random streams of limit orders, market orders, cancels, and replaces, then asserts invariants that a correct exchange can never violate:

- the book never crosses (best bid < best ask, always),
- quantity is conserved (`filled + remaining == original` for every order; maker fills equal taker fills),
- no buyer ever pays above their limit, no seller receives below theirs,
- the depth snapshot always agrees with a brute-force scan of live orders.

When Hypothesis finds a violation it automatically shrinks the failing sequence to a minimal reproduction — the single most effective debugging tool I know of for stateful systems.

## License

MIT
