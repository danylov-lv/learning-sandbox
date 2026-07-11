The sparse index works like this: ClickHouse splits the sorted data into
granules (8192 rows each, by default) and records one index entry per
granule -- essentially "this granule's first row has ORDER BY key >= X".
To answer a query, it binary-searches that (small, in-memory) index to
find which granules could *possibly* contain a matching row, and skips
reading the rest entirely. This only works cleanly when your WHERE clause
constrains a prefix of the key starting from the first column -- an
equality on `category` alone narrows the search to a contiguous range of
granules; adding an equality or range on `product_id` (the next column)
narrows it further *within* that range. A predicate on `scraped_at` alone,
with no `category`/`product_id` constraint, can't narrow anything, because
rows with any `scraped_at` value are scattered across every category and
product's granules.

That's why `in_stock` in `category_instock_agg()` doesn't help you prune
-- it's not in the ORDER BY tuple at all, so every granule needs to be
opened and checked regardless.

For `ch_read_rows`, remember the harness docstring's warning: `count(*)`
in ClickHouse can be satisfied from each part's row-count metadata without
touching any actual column data, so it always reads ~0 rows -- that's true
whether or not the index pruned anything, which makes it useless as your
full-scan "baseline". You need a query that is forced to read real column
bytes even when it can't prune, so the row count you observe reflects
actual scanning work. What aggregate forces that?
