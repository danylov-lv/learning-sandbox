# Hint 2

The query has two jobs for `orders`: find the rows for one `user_id`, and
return them in `created_at DESC` order, cut off at 20. A single-column
index can serve the equality filter, but then Postgres still has to sort
whatever it finds — a `Sort` node materializing before the `Limit`.

Think about a composite index: one that can satisfy the equality filter
*and* hand rows back to the `Limit` already in the right order, so no
separate sort step is needed at all. What column has to lead? What has to
come second, and in which direction?
