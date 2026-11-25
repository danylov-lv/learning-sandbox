Start by just reading the `ORDER BY` on `observations_raw` again:
`(category, product_id, scraped_at)`. In a MergeTree that tuple is not
merely "how the results happen to come out sorted" -- it's how the rows are
physically arranged on disk, and it's what the primary index is built
from. Before writing any SQL, ask yourself: for each of the four functions,
which columns does its WHERE clause touch, and are those columns a
*leading, contiguous prefix* of that ORDER BY tuple, or not?

`category_instock_agg()` filters on `in_stock`. Where does `in_stock` sit
in the ORDER BY tuple? `full_scan_sum()` filters on nothing. `pruned_sum()`
and `one_product_history()` filter on `category` and `product_id` -- where
do those sit? The answer to "does this prune?" falls straight out of that
comparison, before you ever run a query.
