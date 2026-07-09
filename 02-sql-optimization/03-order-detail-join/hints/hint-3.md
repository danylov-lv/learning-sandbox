# Hint 3

You need a new index on `order_items` whose leading column is `order_id`.
Whether you make it a plain single-column index or a composite that also
includes `product_id` (to match the join condition and avoid an extra heap
lookup) is your call — both satisfy the checker, but think about which one
better serves this specific query shape (point lookup by `order_id`, joined
to `products` on `product_id`).

Leave the existing `idx_order_items_product_order` index alone — you are
not asked to remove it, and other, unseen queries may depend on its
`product_id`-first order.
