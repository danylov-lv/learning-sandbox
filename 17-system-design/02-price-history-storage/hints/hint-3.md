# Hint 3

Concrete shape to work toward:

- **Partitioning**: partition by calendar time at a grain coarse enough
  that retention/expiry is "drop a handful of partitions," not "delete
  scattered rows" -- monthly is a common choice for a multi-year table.
- **Ordering/clustering key**: within a partition, order by
  `(product_id, observed_at)` or similar -- product first so a range scan
  for one product is a contiguous run, timestamp second so that run is
  already time-ordered. Say explicitly in `Physical layout` what this
  ordering does to a query that groups by category/day instead of by
  product (it loses the locality it had for the product-first case, and
  you should size that cost using the bad-key overhead figure in
  `workload.json` -- by hand, not a required function).
- **Analytics read**: consider whether it should hit the same table at all,
  or a separate pre-aggregated rollup (e.g. one row per product per day
  with a computed daily delta) that's built once and queried many times,
  instead of scanning raw observations for every analytics query.
- **Write path**: buffer/batch observations before commit, and run
  compaction on a cadence that keeps the average part size well above
  "one write's worth of rows" -- tie the cadence to your daily row volume,
  not to a fixed clock interval chosen arbitrarily.
- **Hot/cold move**: decide whether data physically moves (copy to
  cheaper storage, delete from hot) or whether "hot" and "cold" are just
  two storage classes under one table with a lifecycle rule -- either is
  defensible, but say which and why in `Retention and tiering`.
- **Capacity model order of operations**: `rows_per_day` feeds almost
  everything else -- get that one right first, then retained rows, then
  bytes (raw, then compressed), then the change-only variant as a parallel
  branch, then hot-tier bytes as a subset of the retained total, then cost
  as hot-price times hot-bytes plus cold-price times the remainder.
