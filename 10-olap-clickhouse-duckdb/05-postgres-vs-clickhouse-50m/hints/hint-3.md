Before you decide the Postgres side is "just slow", look at *why*. Open a
psql session (or run it through psycopg) against
`price_history.observations` and prefix your `pg_answer()` query with
`EXPLAIN ANALYZE`. Read what plan node Postgres picked at the top, and
notice there's no index it could have used instead -- the table only
carries a primary key on `observation_id`. That plan is the whole reason
this comparison exists; understanding it is as much the point of this task
as getting the numbers to match ground truth.

On the ClickHouse side, the equivalent question is "which columns did this
query actually touch", not "which index did it use" -- a `MergeTree`
doesn't need a secondary index to avoid reading `product_id`, `seller_id`,
`currency`, or `scraped_at` when your query never references them.
