# Hint 1

`inventory_events` already has a B-tree index on `occurred_at`. That's
enough to make a single "give me the last 14 days" query reasonably fast.
It does nothing at all for the *other* half of this table's problem: a
monthly retention job that needs to delete everything older than N months.
A B-tree index lets you find rows fast; it doesn't let you throw away a
big contiguous chunk of them fast — that's still one row-by-row `DELETE`
walking (and dirtying, and needing vacuum for) however many million rows
match. What Postgres feature turns "delete an old month" into an operation
that costs roughly nothing, regardless of how many rows are in that month?

## Read up on

- Partition pruning (so you understand the second half of this task, not
  just the retention half)
