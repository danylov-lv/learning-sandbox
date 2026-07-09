# Hint 2

`idx_reviews_product_id` is a single-column index on `product_id`. Two
other indexes on the table both start with `product_id` too. Anything the
plain index can do, at least one of those two composites can also do — for
free, since they're already sorted by `product_id` first.

`idx_reviews_review_text` indexes the full review body. Reread the "what
the application does NOT do" section of `src/workload.md`. A B-tree on a
long free-text column is also unusually expensive to store and to update —
worth checking its on-disk size relative to the table.
