Start with what `ReplacingMergeTree(version)` actually promises. It does
NOT promise "at most one row per key, always" -- it promises that WHEN rows
sharing the table's `ORDER BY` key get merged together (a background
process, on its own schedule), only the one with the highest value in the
named version column survives that merge. Nothing forces a merge to happen
at any particular time, and nothing stops you from querying the table in
between merges.

So before writing `deduped_state_query()`, ask yourself: right after
`insert_batch` returns, how many parts does the table likely have, and has
ClickHouse had any reason yet to merge them? What would a plain `SELECT *`
show you in that window -- and would you even be able to tell, just by
looking at the output, whether what you're seeing is already deduped or
not? If you can't tell from the output alone, your query needs to force the
answer instead of hoping for it.
