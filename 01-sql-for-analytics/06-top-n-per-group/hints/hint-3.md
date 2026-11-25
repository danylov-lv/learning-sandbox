Build it in layers:

1. A CTE that walks the category tree from the `Toys & Hobbies` root down to
   its level-2 and level-3 descendants (self-join `categories` to itself:
   root -> level-1 child -> level-2 child -> level-3 child), producing
   `(l2_id, l2_name, leaf_id)` rows — one per level-3 leaf, tagged with its
   level-2 ancestor.
2. A CTE that joins `products` to that leaf list, joins `price_snapshots` on
   `product_id`, joins `sources` and filters `currency = 'USD'`, filters
   `captured_at` to June 2025, and `GROUP BY`s to one row per `(l2_id,
   l2_name, product_id, product_name)` with `MAX(price)`.
3. An outer query that applies `ROW_NUMBER() OVER (PARTITION BY l2_id ORDER
   BY max_price DESC, product_id ASC)` over stage 2, then filters to rank
   `<= 3` and selects the final column list/order named in the README.

Double-check you're joining products to their *leaf* category, not filtering
`categories.level = 2` directly on the product — products only ever attach
at level 3.
