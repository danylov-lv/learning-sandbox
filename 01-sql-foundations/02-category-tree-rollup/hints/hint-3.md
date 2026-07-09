# Hint 3

Shape of the approach:

1. `WITH RECURSIVE subtree AS (...)` producing one row per category, tagged
   with `(root_id, root_name)` and its own `level`, for every category
   reachable from any root.
2. From `subtree`, group by `root_name` to get `subtree_category_count`
   (`COUNT(*)`) and `max_depth` (`MAX(level)`).
3. For `leaf_count`, a category is a leaf if no other row in `categories` has
   it as `parent_id` — express that as a `NOT EXISTS` (or `LEFT JOIN ...
   WHERE ... IS NULL`) against `categories` itself, then count how many such
   leaves fall under each root using the same `subtree` mapping.
4. For `product_count`, join `products.category_id` against `subtree.id`
   (every product's category appears somewhere in `subtree`, since `subtree`
   covers the whole tree) and count per root.
5. Combine the pieces (e.g. as separate CTEs joined on `root_name`), then add
   `product_share_pct` with a window function dividing each root's
   `product_count` by the sum of `product_count` across all roots.
