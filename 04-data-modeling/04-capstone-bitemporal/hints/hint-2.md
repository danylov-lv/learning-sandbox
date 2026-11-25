# Hint 2 (q14: price drops)

A price drop is defined relative to "the immediately preceding
observation on that same listing" — that's a statement about order within
a partition, which is exactly what a window function over `(shop_code,
product_code)` ordered by `event_time` gives you. Getting the previous
row's price next to the current row's price (rather than, say, comparing
every pair of observations, or comparing to some aggregate like a moving
average) is the whole mechanism here.

Two things are easy to get subtly wrong:

- The "previous observation" has to come from the *deduplicated* stream.
  If you compute this window over raw, non-deduplicated rows, an exact
  duplicate sitting next to its original will never look like a drop, but
  a stray near-duplicate might create a phantom one — get the dedup done
  first, then window over what's left.
- The `tracked_since` filter applies per (client, product) pair, to the
  drop's own `event_time` — not to when the client record was created,
  not to the product's discovery date. A client's `tracked_since` for one
  product tells you the earliest `event_time` a drop on *that* product can
  count for *that* client; it says nothing about other clients or other
  products.

Also remember the aggregation direction: a drop is defined per listing
`(shop_code, product_code)`, but the client cares about the product as a
whole, so drops need to be summed across every shop that lists a tracked
product, not just one.
