# Hint 3

Shape of the approach:

1. CTE `cat_root`: join `categories` to itself three times (leaf -> level2 ->
   level1 -> level0) filtering `level = 3` on the starting row, and select
   `(leaf_category_id, root_category_name)`. This CTE has exactly as many
   rows as there are leaf categories.
2. Join `price_snapshots` -> `sources` (filter `currency = 'USD'`, filter the
   June 2025 date window) -> `products` -> `cat_root` (on `products.category_id
   = cat_root.leaf_category_id`).
3. `GROUP BY` root category name and tier, and compute the count/min/avg/max
   aggregates in that single grouped query. Because `cat_root` maps each leaf
   category to exactly one root, this join does not fan out — each snapshot
   row still corresponds to exactly one (root, tier) group.
