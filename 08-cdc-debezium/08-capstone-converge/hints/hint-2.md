# Hint 2

The exactly-once dedup gate and the `mart.cap_meta` aggregate must live in
the SAME mart transaction as the `replica.offers` upsert/delete -- not
three separate commits. If the dedup insert and the aggregate update are
in different transactions, a crash between them leaves you with a state no
clean run could have produced (the row applied but not counted, or counted
but not applied), and CP2's crash injection is specifically aimed at
finding that gap.

The additive schema change is exactly that: additive. `after` on a
pre-ALTER event simply does not have a `"discount_pct"` key; on a
post-ALTER event it does (possibly `null`, if the source row's own
`discount_pct` hasn't been set yet). One dict `.get()` with a default,
applied consistently, is the entire "schema evolution" handling this task
needs on the consumer side -- there is no migration to write, because
`replica.offers` already has the column from the start.

The crash window `_maybe_crash` injects is: the mart transaction (dedup +
upsert/delete + aggregate) has committed; the Kafka offset commit has not
happened yet. That is the redelivery window. Whatever you dedup on
(offset pair or LSN) must be something that is stable and identical across
a redelivery of the exact same message -- not something derived from when
you happened to process it.
