Shape, without handing you the statements verbatim:

- `create_table_with_ttl`: drop-if-exists, then a CREATE TABLE with the
  same 8 columns and ORDER BY as `observations_raw`, plus one extra clause
  after the ORDER BY that names a column, an interval to add to it, and
  the word that means "remove the row" once that sum is in the past
  relative to `now()`.

- `load_from_raw`: one statement, source and destination both named,
  `SELECT *` from one INTO the other -- no WHERE, no row-by-row Python
  loop.

- `force_ttl`: one statement naming your table. Pick either of the two
  mechanisms from hint 2. Both are single commands; neither takes an
  argument beyond the table name (`OPTIMIZE`'s needs a keyword at the end
  meaning "collapse everything into one part", the other needs a keyword
  pair meaning "make the TTL take effect for real"). Run it through
  whichever harness helper executes a statement with no result set.

- `surviving_count_query` / `oldest_surviving_query`: each is a single
  `SELECT <aggregate>(<column>) FROM t04_observations_ttl` returning one
  row, one column -- the aggregate function and column differ between the
  two, matching their names.

Sanity check before you trust the validator: query
`surviving_count_query()` right after `load_from_raw` (before calling
`force_ttl`) and note the number, then call `force_ttl` and query it
again. If the two numbers are identical, either nothing in this corpus is
actually older than 15 months relative to today (check what `now()` and
the oldest `scraped_at` in `observations_raw` actually are), or your
`force_ttl` isn't doing what you think.
