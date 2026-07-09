# Hint 3

Shape of the query, without the actual SQL:

1. Join `price_snapshots` to `sources` to bring in `tier`.
2. `GROUP BY` the truncated week expression and `tier`.
3. In the `SELECT` list, alongside the group keys, compute:
   - a plain row count
   - a distinct count over the product id column
   - a distinct count over a two-column composite of product id and source id
   - an average of `price`, restricted to `currency = 'USD'` via a per-aggregate
     filter clause (not a query-level `WHERE`), rounded to 2 decimals.
4. Cast the truncated week expression to `date` so the output column is a clean date,
   not a timestamp with a spurious `00:00:00`.
5. No `HAVING`, no outer `WHERE` needed beyond the join condition — every week/tier
   combination that has at least one snapshot should appear.
