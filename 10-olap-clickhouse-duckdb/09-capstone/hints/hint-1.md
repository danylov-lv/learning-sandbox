# Hint 1 -- direction

This capstone is not a new mechanism. Every piece of CP1 and CP2 is
something you already built in an earlier task, just recombined:

- The rollup in `create_rollup` / `rollup_query` is task 02's landing table
  + materialized view + collapsing read, under new names. If task 02 is
  fresh, you already know the shape; if it's not, go re-read it before
  starting here.
- `total_price_sum`, `per_category_instock`, and `top_sellers` are plain
  aggregate queries over `observations_raw` -- no materialized view
  involved, no incremental maintenance, just `GROUP BY` and an aggregate
  function. Don't overthink these three; they're the kind of query you'd
  run directly against a dashboard's "as of right now" page.
- CP2's four functions are task 06 again, read_parquet and
  hive_partitioning, just asked to reproduce three more shapes than that
  task did and confirm the pruning proof still holds.

The genuinely new thing this capstone asks for is not a SQL trick -- it's
noticing that CP1 and CP2 are graded against the SAME ground truth, so if
both pass, ClickHouse and DuckDB have been proven to agree with each other
without either one ever being compared to the other directly. Keep that in
mind while you write CP3: the memo isn't asking you to invent an opinion
about ClickHouse vs. DuckDB, it's asking you to write down what CP1/CP2 (and
tasks 05/07/08) already showed you.
