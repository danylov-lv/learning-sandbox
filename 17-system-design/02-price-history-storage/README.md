# 02 -- Price History Storage

## Backstory

The price-monitoring pipeline you sized in task 01 has been running for a
while now, and the business has decided the history is the product: five
years of per-product price observations need to stay queryable, not just
land somewhere and get archived. Two reads matter in practice. The
dominant one is a customer or internal dashboard asking "show me this one
product's full price series over a date range" -- a charting query, narrow
and frequent. The secondary one is analytics asking "which products moved
the most, per category, per day" -- a query that touches a lot of rows but
runs far less often. Underneath both sits a continuous firehose of scrape
observations landing from your producer/consumer spiders, most of which
report a price that hasn't changed since the last check.

You're not writing any code against a live database for this task -- this
module is the whiteboard-interview version of the job. You design the
physical layout (schema, partitioning, ordering/clustering key), the write
path, how both reads are served, the retention and hot/cold tiering
strategy, and you back all of it with a small back-of-the-envelope
capacity model.

## What's given

- `workload.json` -- the committed numbers for this exercise: tracked
  product count, observations per product per day, the fraction of
  observations where the price actually changed, average raw row size,
  columnar compression ratio, retention window, hot-tier window, hot/cold
  per-GB monthly storage prices, a scan-overhead factor for the designed
  ordering key, a scan-overhead factor for a poorly-chosen one, category
  count, and daily analytics query volume.
- `src/estimate.py` -- nine function stubs, each `raise NotImplementedError`,
  each with a docstring stating its units. No formula is written down
  anywhere in the scaffold -- see "Capacity model contract" below for the
  precise spec.
- `DESIGN.md` -- an unfilled template with every required section already
  in place as a `[fill in ...]` placeholder, including the `### Q1`..`### Q8`
  hostile-review subsections.
- `HOSTILE-REVIEW.md` -- the eight hostile-review questions in full; answer
  them inside `DESIGN.md`, not here.
- `tests/validate.py` -- the validator; read it if you want to see exactly
  what's checked, but it won't show you a solution.
- `hints/` -- three levels of hints, none containing a worked formula.

## What's required

1. Fill in every section of `DESIGN.md`, including all eight hostile-review
   answers under `### Q1` .. `### Q8`.
2. Implement all nine functions in `src/estimate.py` per the capacity model
   contract below.

## Capacity model contract

Pin these conventions exactly -- the validator recomputes every formula
independently from the same spec and compares against your output, so any
deviation (wrong constant, extra rounding, a different definition of
"compression ratio") will disagree with it.

- **Days per year**: use exactly `365.25` everywhere a "days per year"
  constant is needed (annualizing the retention window, and the one-year
  range-query window). This constant is fixed convention, not a
  `workload.json` field.
- **Compression ratio convention**: `compressed_bytes = raw_bytes /
  compression_ratio`. A ratio of 6.4 means the compressed size is
  raw-size divided by 6.4.
- **GB**: 1 GB = 1,000,000,000 bytes (decimal), never GiB, wherever a
  function's output or a per-GB price is involved.
- **No rounding anywhere**: every function returns the raw float result of
  its formula. Do not round, floor, ceil, or truncate at any step.
- **Change-only variant**: assumes the same `avg_row_bytes` and
  `compression_ratio` as the full variant (the column set is unchanged --
  only the row count drops), and assumes *only* rows where the price
  changed are stored -- no periodic checkpoint/snapshot rows on top.
- **Hot tier**: always holds full (non-change-only) observations at
  compressed size, regardless of whatever the change-only comparison in
  your design doc concludes. The change-only variant is evaluated
  separately and does not feed the hot/cold cost model.
- **Cold tier**: the remainder of the retention window at full fidelity,
  compressed -- i.e. `compressed_bytes_retained - hot_tier_bytes`.
- **Range-query model**: `range_query_bytes_scanned` models the *good*
  ordering key case only -- one product's rows across a full one-year
  window, at compressed size, multiplied by
  `good_key_scan_overhead_factor` (a factor > 1 that accounts for a
  granule/row-group not perfectly aligning with a single product's rows
  even under the right key). There is no required function for the
  bad-key case -- work that out by hand in `DESIGN.md` from
  `tracked_products`, `observations_per_product_per_day`,
  `avg_row_bytes`, `compression_ratio`, and `bad_key_scan_overhead_factor`
  (the full one-year, all-products compressed footprint, times that
  factor), to quantify what the wrong key would cost the same query.

Function-by-function:

1. **`rows_per_day(w)`** -- `tracked_products * observations_per_product_per_day`.
2. **`rows_retained(w)`** -- `rows_per_day(w) * retention_years * 365.25`.
3. **`raw_bytes_retained(w)`** -- `rows_retained(w) * avg_row_bytes`.
4. **`compressed_bytes_retained(w)`** -- `raw_bytes_retained(w) / compression_ratio`.
5. **`change_only_rows_per_day(w)`** -- `rows_per_day(w) * price_change_fraction`.
6. **`change_only_compressed_bytes_retained(w)`** --
   `change_only_rows_per_day(w) * retention_years * 365.25 * avg_row_bytes / compression_ratio`.
7. **`hot_tier_bytes(w)`** --
   `rows_per_day(w) * hot_tier_days * avg_row_bytes / compression_ratio`.
8. **`monthly_storage_cost_usd(w)`** --
   `(hot_tier_bytes(w) / 1e9) * hot_tier_price_usd_per_gb_month + ((compressed_bytes_retained(w) - hot_tier_bytes(w)) / 1e9) * cold_tier_price_usd_per_gb_month`.
9. **`range_query_bytes_scanned(w)`** --
   `observations_per_product_per_day * 365.25 * avg_row_bytes / compression_ratio * good_key_scan_overhead_factor`.

## Completion criteria

Run, from the module root:

```bash
cd 17-system-design
uv run python 02-price-history-storage/tests/validate.py
```

It checks, in order:

- Every function in `src/estimate.py` exists and is callable.
- Every function's return value against the validator's own independent
  recomputation of the pinned formula, on the committed `workload.json`
  plus two perturbed variants built in memory -- so a hardcoded constant
  that happens to match the shipped workload will still fail here.
- `DESIGN.md`'s required `## ` sections are present, long enough, and free
  of leftover `[fill in ...]` markers.
- `DESIGN.md` names enough of the concrete grounding vocabulary for this
  design (partitioning, ordering/clustering key, compression, hot/cold
  tiering, compaction, backfill, change-only storage, and related terms).
- `DESIGN.md` makes enough distinct quantitative claims -- this is a
  numbers-backed design, not just prose.
- All eight `### Q1` .. `### Q8` hostile-review subsections are genuinely
  answered -- not missing, not a placeholder, not a verbatim copy of the
  question, and not too short.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Columnar compression and encoding (dictionary, delta, run-length)
- Partition pruning and how a query planner decides what to skip
- Sorting/clustering keys and why column order in the key matters
- Hot-cold storage tiering and what physically moves at the boundary
- Write amplification and compaction in append-heavy columnar layouts
- Change-data/delta storage vs full-fidelity storage, and reconstruction
  cost at read time
- Late-arriving data (backfills) and how it interacts with already-sealed
  partitions and downstream caches

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution -- there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
