Concrete shape for each function, without handing you the SQL:

- `category_instock_agg()`: a single `SELECT ... FROM observations_raw
  WHERE in_stock = 1 GROUP BY category` with three expressions in the
  SELECT list -- the group key, a `count(*)`-style expression, and an
  `avg(price)`-style expression, in that order. Nothing about GROUP BY or
  aggregate functions here is ClickHouse-specific; standard SQL works.

- `full_scan_sum()`: `SELECT sum(price) FROM observations_raw` -- literally
  nothing else. No WHERE clause at all is the simplest way to guarantee no
  accidental pruning sneaks in and skews your baseline.

- `pruned_sum(category, max_product_id)`: same `SELECT sum(price) FROM
  observations_raw`, but now add `WHERE category = '<category>' AND
  product_id < <max_product_id>`. You're given a Python `str` and `int` --
  build the SQL string with an f-string or `.format()`; just remember the
  category needs to be a quoted string literal in the generated SQL, the
  integer does not.

- `one_product_history(category, product_id)`: `SELECT scraped_at, price
  FROM observations_raw WHERE category = '<category>' AND product_id =
  <product_id> ORDER BY scraped_at`. Two columns, in that order, is what
  the validator expects.

Once all four return valid SQL, sanity-check by hand: run
`full_scan_sum()` and `pruned_sum('electronics', 50)` yourself against a
live client and just eyeball the two `sum(price)` numbers if you like --
but the thing to actually watch is what `ch_read_rows()` reports for each,
since that's what the validator grades. If `pruned_sum` isn't reading
dramatically fewer rows than `full_scan_sum`, re-check that the predicate
you wrote really does start from `category` -- a predicate that only
touches `product_id` (skipping `category`) does not get to use the index
the same way, because it isn't a prefix of the ORDER BY tuple starting
from column one.
