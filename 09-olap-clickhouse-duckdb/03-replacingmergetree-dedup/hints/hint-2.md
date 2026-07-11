Two independent ways to make a read merge-independent -- pick one, don't
mix them:

- ClickHouse has a query-time modifier you can attach to a table reference
  in the FROM clause specifically to force ReplacingMergeTree's collapsing
  logic to run on-the-fly, over whatever parts currently exist, before
  returning rows. It's a single keyword, not a function call. Look at how
  it's used in ClickHouse's own docs for `ReplacingMergeTree` -- notice
  where in the query it goes and what it costs (it has to actually merge
  data at read time, which is not free, especially with many unmerged
  parts).
- Alternatively, ignore the engine's special semantics entirely and treat
  the table as a plain pile of rows: `GROUP BY` the natural key, and for
  each of `price` and `in_stock`, pick the value that belongs to the row
  with the maximum `version` in that group. ClickHouse has a family of
  aggregate functions built exactly for "give me the value of column A that
  corresponds to the max of column B, within this group" -- it's not a
  window function and it's not `MAX(price)` (which would give you the
  highest PRICE, not the price of the highest-VERSION row -- a subtly
  different, wrong answer). Search for that function family by name.

For `count_before_merge()` and `count_after_dedup()`: the "before" count is
the simplest aggregate you can write with no WHERE and no GROUP BY at all.
The "after" count needs to answer "how many distinct keys are there", not
"how many rows are there after some particular row per key was picked" --
there's more than one syntactically different way to express that in SQL,
and either is fine as long as it doesn't quietly depend on FINAL having
already been applied somewhere it wasn't.
