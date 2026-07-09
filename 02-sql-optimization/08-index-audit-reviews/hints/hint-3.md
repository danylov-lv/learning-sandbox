# Hint 3

Two `DROP INDEX` statements, targeting the plain `product_id` index and the
`review_text` index. Leave both `(product_id, created_at)` and
`(product_id, rating)` in place — pattern 1 needs the first, pattern 2
needs the second, and pattern 3 (a bare count) can be served by either.

Before you drop anything for real, double-check in `pg_stat_user_indexes`
(`idx_scan` column) that the indexes you're about to remove are, in fact,
barely or never scanned — that's the empirical confirmation to go with the
workload-based reasoning.
