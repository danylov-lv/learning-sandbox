# Hint 2

The mechanism: compute two row numbers over the same partition
(`product_id, source_id`), ordered by `captured_at`.

- Row number A: ordered over *all* rows in the partition, regardless of `in_stock`.
- Row number B: ordered over rows in a partition that also includes `in_stock` as a
  partition key (so it restarts counting whenever `in_stock` flips).

Within a single unbroken run of the same `in_stock` value, A and B both increment by
exactly 1 per row, so `A - B` is constant for the whole run and changes the moment the
run breaks. That constant becomes your group id — group by
`(product_id, source_id, in_stock, A - B)` and filter to `in_stock = false` either
before or after grouping.

From there it's a normal aggregation per group: count of rows, min and max of
`captured_at`.
