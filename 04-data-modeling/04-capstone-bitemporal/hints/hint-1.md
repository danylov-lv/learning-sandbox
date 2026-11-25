# Hint 1 (CP1: late data)

Lag is not a property of a shop, a product, or even a listing — it's a
property of a single observation row. Two observations on the same
listing, seconds apart in `event_time`, can have wildly different
`ingested_at` delays. That means whatever answers q13a/q13b needs both
timestamps sitting on (or reachable from) the row itself, not derived or
reconstructed after the fact.

Ask yourself plainly: does a query against your current schema know, for
any given observation, both "when did this price change happen" and "when
did my system find out about it"? If the answer is no, that's the actual
work of this checkpoint — everything else is downstream of having that.

For q13b, think about what "as published on date D" means as a predicate,
not as a vague idea. A report "published" using only data ingested by a
cutoff is exactly the set of rows satisfying `ingested_at <= cutoff` —
nothing about `event_time` changes; you're not filtering which events
happened, you're filtering which events your system *knew about* by that
moment. Confusing the two timestamps here is the single most common way
to make q13b come out wrong (or worse, come out looking right by
producing two identical columns instead of the guaranteed difference).
