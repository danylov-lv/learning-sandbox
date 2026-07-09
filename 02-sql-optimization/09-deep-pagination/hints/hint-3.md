# Hint 3

Postgres supports row-value comparisons directly: `WHERE (a, b) < (x, y)`
means "a < x, or a = x and b < y" — exactly the lexicographic ordering
`ORDER BY a DESC, b DESC` produces, if you pick the matching comparison
direction. Apply that shape to `(occurred_at, id)` against
`(%(cursor_occurred_at)s, %(cursor_id)s)`, keep the same `ORDER BY ...
LIMIT 100`, and drop `OFFSET` entirely.

On the supporting index question: the existing `idx_inventory_events_occurred_at`
index is single-column. Check with `EXPLAIN` whether Postgres can still push
the row-value comparison down as an efficient index condition on that one
column plus a cheap in-memory filter for the tie-break, or whether it falls
back to something that still has to sort or scan more than a handful of
rows. If it's the latter, think about what a composite index leading with
`occurred_at` and including `id` as the second key would let the planner do
with that same row-value predicate directly as an index condition, no
filter needed.
